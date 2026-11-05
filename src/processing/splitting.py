"""processing.splitting - Steam showcase fragmentation.

Every preset goes through the same pipeline:

1. The source (GIF, video or still image) is scaled to the preset canvas
   without distortion (fill + center crop, or keep aspect when the height
   is free) and cut into its parts with FFmpeg filters. The source is
   decoded once for all its parts (one FFmpeg run with a split graph).
2. All animated parts are encoded together with ONE shared frame rate and
   quality, so the pieces stay in sync when Steam shows them side by side:
   gifski with a search on quality (best result), or an FFmpeg palette
   ladder when gifski is not installed. Both try the best setting with every
   piece first (one pass when it fits), then search with the heaviest piece
   alone and encode the others only at its answer (see _shared_search).
3. Each part must fit under Steam's 5 MiB limit; the final files get the
   Steam trailer patch and a manifest.json describing the run.
"""
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from gif_utils import format_fps, open_image, playback_fps, read_timing
from processing.common import (FRAGMENT_MAX_BYTES, CancelFn, check_cancel, logger,
                               run_tool, tail)
from video_utils import IMAGE_EXTS, is_video, probe_video

#: Frame-rate caps tried after the source rate, from smoothest to smallest.
_FPS_TIERS = (24, 20, 15, 12, 10, 8, 6, 4, 3)
#: FFmpeg fallback ladder: (palette colours, fps cap or None = source rate).
#: Every step lowers the colours, the frame rate or both, so sizes only shrink.
_FFMPEG_LADDER = ((256, None), (256, 24), (192, 24), (160, 20), (128, 20), (96, 15),
                  (64, 12), (64, 8), (48, 8), (32, 6), (24, 5), (16, 4), (16, 3))
#: gifski quality range searched for the best value that fits.
_GIFSKI_QUALITY = (10, 95)
#: Videos are fragmented at most at this rate (GIF size grows with every frame).
_VIDEO_FPS_CAP = 30.0

ProgressFn = Optional[Callable[[str], None]]


@dataclass
class _EncodeJob:
    """One output GIF of a shared encode: source + filters -> output.

    ``canvas`` is applied once per source and shared by its jobs (the scale to
    the preset canvas); ``filters`` is the job's own part (its crop).
    ``pixels`` (output area) lets the encoders check the biggest piece first.
    """
    source: Path
    filters: str   # FFmpeg filters of this output, after fps and canvas ("" for none)
    output: Path
    canvas: str = ""
    pixels: int = 0


class _EncoderFailed(Exception):
    """FFmpeg itself failed (not a size problem): stop the search."""


def shared_graph(fps_arg: str, canvas: str, branches: List[str]) -> Tuple[str, List[str]]:
    """filter_complex that decodes a source once and feeds one output per branch.

    Returns (graph, output labels): ``[0:v]fps,canvas,split=N`` then each
    branch's own filters, so N pieces cost one decode and one scale.
    """
    head = ",".join(f for f in (f"fps={fps_arg}", canvas) if f)
    if len(branches) == 1:
        return f"[0:v]{head},{branches[0] or 'null'}[o0]", ["[o0]"]
    count = len(branches)
    labels = "".join(f"[s{i}]" for i in range(count))
    graph = [f"[0:v]{head},split={count}{labels}"]
    graph += [f"[s{i}]{branch or 'null'}[o{i}]" for i, branch in enumerate(branches)]
    return ";".join(graph), [f"[o{i}]" for i in range(count)]


class SplitMixin:
    # Layouts verified on the Steam profile. Each preset defines:
    #   parts:       (name, width_px, left_offset_px) crops of the scaled canvas
    #   total_w:     canvas width the source is scaled to before cropping
    #   fixed_h:     canvas height (None = keep the source aspect ratio)
    #   upload_hint: upload mode: "artwork", "screenshot" or "workshop"
    #   spoof_dims:  upload with fake 1000x1 dimensions (ultra-wide banners)
    SHOWCASE_PRESETS = {
        # 5 columns of one 638x354 image; built from config (steam_profile)
        "workshop_5part": {
            "parts": [(f"part_{i + 1}", 127, 127 * i) for i in range(5)],
            "total_w": 638, "fixed_h": 354,
            "upload_hint": "workshop",
            "desc": "Workshop Showcase 5 partes (638x354)",
        },
        "featured_630": {
            "parts": [("featured", 630, 0)], "total_w": 630, "fixed_h": None,
            "upload_hint": "artwork",
            "desc": "Featured Artwork 630xH (1 slot grande)",
        },
        "artwork_single_630": {
            "parts": [("single", 630, 0)], "total_w": 630, "fixed_h": 354,
            "upload_hint": "artwork",
            "desc": "Artwork single 630x354 (16:9)",
        },
        "screenshot_638": {
            "parts": [("screenshot", 638, 0)], "total_w": 638, "fixed_h": 354,
            "upload_hint": "screenshot",
            "desc": "Screenshot Showcase 638x354 (1 slot)",
        },
        # main + side; built from config (artwork_showcase)
        "artwork_2part": {
            "parts": [("artwork_main", 506, 0), ("artwork_side", 100, 506)],
            "total_w": 606, "fixed_h": None,
            "upload_hint": "artwork",
            "desc": "Artwork 506+100 (main+side, alto libre)",
        },
        "artwork_4grid": {
            "parts": [(f"artwork_g{i + 1}", 245, 245 * i) for i in range(4)],
            "total_w": 980, "fixed_h": 245,
            "upload_hint": "artwork",
            "desc": "Artwork 4-grid 4x245 cuadrados",
        },
        "screenshot_4grid": {
            "parts": [(f"ss_g{i + 1}", 638, 638 * i) for i in range(4)],
            "total_w": 2552, "fixed_h": 354,
            "upload_hint": "screenshot",
            "desc": "Screenshot 4-grid 4x638x354",
        },
        "workshop_5slot_150": {
            "parts": [(f"ws_s{i + 1}", 150, 150 * i) for i in range(5)],
            "total_w": 750, "fixed_h": 150,
            "upload_hint": "workshop",
            "desc": "Workshop Showcase 5x150x150",
        },
        "workshop_5slot_119": {
            "parts": [(f"ws_s{i + 1}", 119, 119 * i) for i in range(5)],
            "total_w": 595, "fixed_h": 119,
            "upload_hint": "workshop",
            "desc": "Workshop Showcase 5x119x119 (tamano nativo)",
        },
        "panorama_5_630": {
            "parts": [(f"pano_{i + 1}", 630, 630 * i) for i in range(5)],
            "total_w": 3150, "fixed_h": 360,
            "upload_hint": "artwork", "spoof_dims": True,
            "desc": "Panorama artwork 5x630x360 (banner horizontal)",
        },
    }

    # ------------------------------------------------------------------
    # Presets
    # ------------------------------------------------------------------
    def preset_config(self, key: str) -> dict:
        """Return the layout of a preset, applying the user's config overrides."""
        if key not in self.SHOWCASE_PRESETS:
            raise KeyError(f"Preset desconocido: {key}")
        cfg = dict(self.SHOWCASE_PRESETS[key])
        if key == "workshop_5part":
            width = int(self.config.get("steam_profile.width", 638))
            height = int(self.config.get("steam_profile.height", 354))
            count = max(1, int(self.config.get("steam_profile.parts", 5)))
            section = width // count
            cfg.update(total_w=width, fixed_h=height,
                       parts=[(f"part_{i + 1}", section, section * i) for i in range(count)])
        elif key == "artwork_2part":
            main = int(self.config.get("artwork_showcase.main_width", 506))
            side = int(self.config.get("artwork_showcase.side_width", 100))
            height = int(self.config.get("artwork_showcase.height", 0) or 0)
            cfg.update(total_w=main + side, fixed_h=height or None,
                       parts=[("artwork_main", main, 0), ("artwork_side", side, main)])
        return cfg

    # ------------------------------------------------------------------
    # Public entry points
    # ------------------------------------------------------------------
    def fragment_media(self, source: Path, preset: str, output_dir: Optional[Path] = None,
                       progress_cb: ProgressFn = None, should_cancel: CancelFn = None) -> bool:
        """Cut a GIF, video or still image into the parts of ``preset``.

        Output goes to <stem>_workshop/fragmentos/ (emptied first). Returns
        True on success; on failure the reason is in ``_last_split_error``.
        Raises InterruptedError when ``should_cancel`` returns True.
        """
        self._last_split_error = ""
        source = Path(source)
        try:
            cfg = self.preset_config(preset)
        except KeyError as e:
            self._last_split_error = str(e)
            return False
        if not self.check_ffmpeg():
            self._last_split_error = "FFmpeg no esta disponible"
            return False

        out_dir = Path(output_dir) if output_dir else self._workspace_dir(source, "fragmentos")
        out_dir.mkdir(parents=True, exist_ok=True)
        self._archive_before_overwrite(out_dir, protect=source)
        logger.info("Fragmentando %s con el preset %s", source.name, preset)

        if source.suffix.lower() in IMAGE_EXTS:
            return self._split_static(source, preset, cfg, out_dir)

        try:
            width, height, fps = self._source_geometry(source)
        except (OSError, ValueError) as e:
            self._last_split_error = f"No se pudo leer {source.name}: {e}"
            return False
        canvas_h, canvas = self._canvas_filter(cfg, width, height)
        jobs = [_EncodeJob(source, f"crop={w}:{canvas_h}:{left}:0",
                           out_dir / f"{source.stem}_{name}.gif",
                           canvas=canvas, pixels=w * canvas_h)
                for name, w, left in cfg["parts"]]

        try:
            result = self._encode_shared(jobs, fps, FRAGMENT_MAX_BYTES, progress_cb, should_cancel)
        except InterruptedError:
            for job in jobs:  # never leave half a set behind
                job.output.unlink(missing_ok=True)
            raise
        if result is None:
            if not self._last_split_error:
                self._last_split_error = ("No se pudo generar ningun fragmento por debajo de 5 MB. "
                                          "Recorta la duracion del clip.")
            return False

        for job in jobs:
            self._patch_gif_trailer(job.output)
        self._write_manifest(out_dir, f"showcase_{preset}",
                             {"preset": preset, "total_w": cfg["total_w"], "height": canvas_h,
                              **result},
                             archivos=[job.output for job in jobs], fuente=source)
        logger.info("Preset %s completado: %d parte(s) [%s]", preset, len(jobs), result)
        return True

    # ------------------------------------------------------------------
    # Geometry
    # ------------------------------------------------------------------
    @staticmethod
    def _source_geometry(source: Path) -> Tuple[int, int, float]:
        """(width, height, fps to encode at) of an animated source."""
        if is_video(source):
            info = probe_video(source)
            fps = info.fps if info.fps > 0 else 24.0
            return info.width, info.height, min(fps, _VIDEO_FPS_CAP)
        timing = read_timing(source)
        return timing.width, timing.height, playback_fps(source)

    @staticmethod
    def _canvas_filter(cfg: dict, width: int, height: int) -> Tuple[int, str]:
        """(canvas height, FFmpeg filters) that bring the source to the preset canvas."""
        total_w = cfg["total_w"]
        if cfg["fixed_h"]:
            canvas_h = int(cfg["fixed_h"])
            return canvas_h, (f"scale={total_w}:{canvas_h}:force_original_aspect_ratio=increase"
                              f":flags=lanczos,crop={total_w}:{canvas_h}")
        # Free height: keep the aspect ratio (even height for the encoders).
        canvas_h = max(2, 2 * round(height * total_w / max(1, width) / 2))
        return canvas_h, f"scale={total_w}:{canvas_h}:flags=lanczos"

    # ------------------------------------------------------------------
    # Shared encoder (also used by the size optimiser)
    # ------------------------------------------------------------------
    def _encode_shared(self, jobs: List[_EncodeJob], source_fps: float, max_bytes: int,
                       progress_cb: ProgressFn = None, should_cancel: CancelFn = None
                       ) -> Optional[dict]:
        """Encode all jobs with one shared fps/quality so every output fits ``max_bytes``.

        Returns {"engine", "fps", "quality" | "colors"} or None.
        """
        tiers = [source_fps] + [t for t in _FPS_TIERS if t < source_fps - 0.5]
        if self.check_gifski():
            result = self._encode_shared_gifski(jobs, tiers, max_bytes, progress_cb, should_cancel)
            if result is not None:
                return result
            logger.warning("gifski no consiguio un resultado valido, usando FFmpeg")
        return self._encode_shared_ffmpeg(jobs, source_fps, max_bytes, progress_cb, should_cancel)

    def _encode_shared_gifski(self, jobs, tiers, max_bytes, progress_cb, should_cancel):
        work = Path(tempfile.mkdtemp(prefix="wkart_frag_"))
        qualities = list(range(_GIFSKI_QUALITY[1], _GIFSKI_QUALITY[0] - 1, -1))  # best first
        try:
            for fps in tiers:
                fps_arg = format_fps(fps)
                frame_dirs = self._extract_job_frames(jobs, fps_arg, work, should_cancel)
                if frame_dirs is None:
                    return None
                # The piece with the heaviest frames gives the heaviest GIF: it goes first.
                weight = [sum(f.stat().st_size for f in folder.glob("frame*.png"))
                          for folder in frame_dirs]
                order = sorted(range(len(jobs)), key=lambda i: (-weight[i], -jobs[i].pixels))
                reported = set()

                def encode(index: int, candidate: int) -> int:
                    quality, job = qualities[candidate], jobs[index]
                    if quality not in reported:
                        reported.add(quality)
                        _report(progress_cb, f"gifski: {fps_arg} fps, calidad {quality}")
                    check_cancel(should_cancel)
                    result = run_tool([self.gifski_path, "--fps", fps_arg, "--quality", str(quality),
                                       "--repeat", "0", "-o", job.output,
                                       frame_dirs[index] / "frame*.png"],
                                      timeout=900, should_cancel=should_cancel)
                    if result.returncode != 0 or not job.output.exists():
                        logger.warning("gifski fallo (%s): %s", job.output.name, tail(result.stderr))
                        raise _EncoderFailed
                    return job.output.stat().st_size

                try:
                    best = _shared_search(len(qualities), order, encode, max_bytes,
                                          *_keepers(jobs, work))
                except _EncoderFailed:
                    return None
                finally:
                    for folder in frame_dirs:
                        shutil.rmtree(folder, ignore_errors=True)
                if best is not None:
                    return {"engine": "gifski", "fps": fps_arg, "quality": qualities[best]}
                logger.info("gifski: a %s fps no cabe en %.2f MB, bajando fps",
                            fps_arg, max_bytes / 1048576)
            return None
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def _extract_job_frames(self, jobs: List[_EncodeJob], fps_arg: str, work: Path,
                            should_cancel: CancelFn) -> Optional[List[Path]]:
        """PNG frames of every job, one FFmpeg run (one decode) per source."""
        folders: List[Optional[Path]] = [None] * len(jobs)
        groups: Dict[Tuple[Path, str], List[int]] = {}
        for index, job in enumerate(jobs):
            groups.setdefault((job.source, job.canvas), []).append(index)
        for (source, canvas), indexes in groups.items():
            check_cancel(should_cancel)
            graph, labels = shared_graph(fps_arg, canvas, [jobs[i].filters for i in indexes])
            cmd = [self.ffmpeg_path, "-hide_banner", "-y", "-i", source,
                   "-filter_complex", graph]
            for label, index in zip(labels, indexes):
                folder = work / f"fps{fps_arg}_{index}"
                folder.mkdir()
                folders[index] = folder
                cmd += ["-map", label, folder / "frame%06d.png"]
            result = run_tool(cmd, timeout=600 + 300 * len(indexes), should_cancel=should_cancel)
            if result.returncode != 0 or not all(any(folders[i].glob("frame*.png"))
                                                 for i in indexes):
                self._last_split_error = f"FFmpeg no pudo extraer los frames: {tail(result.stderr)}"
                return None
        return folders

    def _encode_shared_ffmpeg(self, jobs, source_fps, max_bytes, progress_cb, should_cancel):
        ladder = [(colors, cap) for colors, cap in _FFMPEG_LADDER
                  if cap is None or cap < source_fps - 0.5]
        work = Path(tempfile.mkdtemp(prefix="wkart_ffl_"))
        order = sorted(range(len(jobs)), key=lambda i: -jobs[i].pixels)
        reported = set()

        def encode(index: int, step: int) -> int:
            colors, cap = ladder[step]
            fps_arg, job = format_fps(cap or source_fps), jobs[index]
            if step not in reported:
                reported.add(step)
                _report(progress_cb, f"FFmpeg: {fps_arg} fps, {colors} colores")
            check_cancel(should_cancel)
            graph = ",".join(f for f in (f"[0:v]fps={fps_arg}", job.canvas, job.filters) if f)
            graph += (f",split[a][b];[a]palettegen=max_colors={colors}:stats_mode=full"
                      f":reserve_transparent=1[p];"
                      f"[b][p]paletteuse=dither=sierra2_4a:diff_mode=rectangle")
            result = run_tool([self.ffmpeg_path, "-hide_banner", "-y", "-i", job.source,
                               "-filter_complex", graph, "-loop", "0", job.output],
                              timeout=900, should_cancel=should_cancel)
            if result.returncode != 0 or not job.output.exists():
                self._last_split_error = f"FFmpeg fallo: {tail(result.stderr)}"
                raise _EncoderFailed
            return job.output.stat().st_size

        try:
            best = _shared_search(len(ladder), order, encode, max_bytes, *_keepers(jobs, work))
        except _EncoderFailed:
            return None
        finally:
            shutil.rmtree(work, ignore_errors=True)
        if best is None:
            return None
        colors, cap = ladder[best]
        return {"engine": "ffmpeg", "fps": format_fps(cap or source_fps), "colors": colors}

    # ------------------------------------------------------------------
    # Still images -> JPEG parts
    # ------------------------------------------------------------------
    def _split_static(self, image: Path, preset: str, cfg: dict, out_dir: Path) -> bool:
        try:
            with open_image(image) as img:
                width, height = img.size
        except OSError as e:
            self._last_split_error = f"No se pudo abrir la imagen: {e}"
            return False
        canvas_h, canvas = self._canvas_filter(cfg, width, height)
        created = []
        for name, w, left in cfg["parts"]:
            out_path = out_dir / f"{image.stem}_{name}.jpg"
            result = run_tool([self.ffmpeg_path, "-hide_banner", "-y", "-i", image,
                               "-vf", f"{canvas},crop={w}:{canvas_h}:{left}:0",
                               "-q:v", "2", out_path], timeout=120)
            if result.returncode != 0 or not out_path.exists():
                self._last_split_error = f"FFmpeg fallo en {name}: {tail(result.stderr)}"
                return False
            created.append(out_path)
        self._write_manifest(out_dir, f"showcase_{preset}",
                             {"preset": preset, "total_w": cfg["total_w"], "height": canvas_h,
                              "engine": "jpeg"},
                             archivos=created, fuente=image)
        return True


def _shared_search(count: int, order: List[int], encode: Callable[[int, int], int],
                   max_bytes: int, keep: Callable[[int], None],
                   restore: Callable[[int], None]) -> Optional[int]:
    """First (best) of ``count`` candidates at which every job fits ``max_bytes``.

    Candidates go from best to worst quality, so sizes shrink as the index
    grows; ``encode(job, candidate)`` writes the job's output and returns its
    size. ``order`` lists the jobs heaviest first.

    The best candidate is tried with every job: a single pass when all fit.
    Otherwise the job that did not fit (the "pilot") is searched on its own -
    one encode per step instead of one per job, its smallest candidate first
    so a set that cannot fit is rejected at once - and the other jobs are only
    encoded at the pilot's answer. One of them not fitting there becomes the
    next pilot, for the worse candidates only. ``keep(job)`` / ``restore(job)``
    save and bring back a job's output; every job's output is left at the
    returned candidate.
    """
    if count <= 0 or not order:
        return None
    at: Dict[int, int] = {}    # job -> candidate its output file holds now
    kept: Dict[int, int] = {}  # job -> candidate of its saved copy (always a fit)

    def fits(job: int, candidate: int) -> bool:
        size = encode(job, candidate)
        at[job] = candidate
        return size <= max_bytes

    def first_fit(job: int, low: int) -> Optional[int]:
        high = count - 1
        if low > high or not fits(job, high):
            return None
        keep(job)
        kept[job] = best = high
        high -= 1
        while low <= high:
            mid = (low + high) // 2
            if fits(job, mid):
                keep(job)
                kept[job] = best = mid
                high = mid - 1
            else:
                low = mid + 1
        return best

    pilot = next((job for job in order if not fits(job, 0)), None)
    best = 0
    while pilot is not None:
        best = first_fit(pilot, best + 1)
        if best is None:
            return None
        pilot = None
        for job in order:
            if at.get(job) == best:
                continue
            if kept.get(job) == best:
                restore(job)
                at[job] = best
            elif not fits(job, best):
                pilot = job
                break
    return best


def _keepers(jobs: List[_EncodeJob], work: Path):
    """(keep, restore) callbacks of _shared_search that copy a job's output aside."""
    def keep(index: int) -> None:
        shutil.copyfile(jobs[index].output, work / f"keep_{index}.gif")

    def restore(index: int) -> None:
        shutil.copyfile(work / f"keep_{index}.gif", jobs[index].output)

    return keep, restore


def _report(progress_cb: ProgressFn, message: str) -> None:
    logger.info(message)
    if progress_cb:
        try:
            progress_cb(message)
        except Exception:  # a UI callback must never break the encoder
            pass

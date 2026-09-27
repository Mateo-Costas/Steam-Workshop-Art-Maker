"""processing.splitting - Steam showcase fragmentation.

Every preset goes through the same pipeline:

1. The source (GIF, video or still image) is scaled to the preset canvas
   without distortion (fill + center crop, or keep aspect when the height
   is free) and cut into its parts with FFmpeg filters.
2. All animated parts are encoded together with ONE shared frame rate and
   quality, so the pieces stay in sync when Steam shows them side by side:
   gifski with a binary search on quality (best result), or an FFmpeg
   palette ladder when gifski is not installed.
3. Each part must fit under Steam's 5 MiB limit; the final files get the
   Steam trailer patch and a manifest.json describing the run.
"""
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from gif_utils import format_fps, playback_fps, read_timing
from processing.common import FRAGMENT_MAX_BYTES, logger, run_tool, tail
from video_utils import IMAGE_EXTS, is_video, probe_video

#: Frame-rate caps tried after the source rate, from smoothest to smallest.
_FPS_TIERS = (24, 20, 15, 12, 10, 8, 6, 4, 3)
#: FFmpeg fallback ladder: (palette colours, fps cap or None = source rate).
_FFMPEG_LADDER = ((256, None), (256, 24), (192, 24), (160, 20), (128, 20), (96, 15),
                  (64, 12), (64, 8), (48, 8), (32, 6), (24, 5), (16, 4), (16, 3))
#: Videos are fragmented at most at this rate (GIF size grows with every frame).
_VIDEO_FPS_CAP = 30.0

ProgressFn = Optional[Callable[[str], None]]
CancelFn = Optional[Callable[[], bool]]


@dataclass
class _EncodeJob:
    """One output GIF of a shared encode: source + filters -> output."""
    source: Path
    filters: str   # FFmpeg filters applied after the fps filter ("" for none)
    output: Path


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
        jobs = [_EncodeJob(source, f"{canvas},crop={w}:{canvas_h}:{left}:0",
                           out_dir / f"{source.stem}_{name}.gif")
                for name, w, left in cfg["parts"]]

        result = self._encode_shared(jobs, fps, FRAGMENT_MAX_BYTES, progress_cb, should_cancel)
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
        try:
            for fps in tiers:
                fps_arg = format_fps(fps)
                frame_dirs = []
                for index, job in enumerate(jobs):
                    _check_cancel(should_cancel)
                    folder = work / f"fps{fps_arg}_{index}"
                    folder.mkdir()
                    filters = ",".join(f for f in (f"fps={fps_arg}", job.filters) if f)
                    result = run_tool([self.ffmpeg_path, "-hide_banner", "-y", "-i", job.source,
                                       "-vf", filters, folder / "frame%06d.png"], timeout=900)
                    if result.returncode != 0 or not any(folder.glob("frame*.png")):
                        self._last_split_error = f"FFmpeg no pudo extraer los frames: {tail(result.stderr)}"
                        return None
                    frame_dirs.append(folder)

                best_quality = None
                low, high = 10, 95
                while low <= high:
                    quality = (low + high) // 2
                    _report(progress_cb, f"gifski: {fps_arg} fps, calidad {quality}")
                    if self._gifski_all_fit(jobs, frame_dirs, fps_arg, quality, max_bytes,
                                            work, should_cancel):
                        best_quality = quality
                        for job in jobs:
                            shutil.copyfile(job.output, work / f"best_{job.output.name}")
                        low = quality + 1
                    else:
                        high = quality - 1
                for folder in frame_dirs:
                    shutil.rmtree(folder, ignore_errors=True)
                if best_quality is not None:
                    for job in jobs:
                        shutil.copyfile(work / f"best_{job.output.name}", job.output)
                    return {"engine": "gifski", "fps": fps_arg, "quality": best_quality}
                logger.info("gifski: a %s fps no cabe en %.2f MB, bajando fps",
                            fps_arg, max_bytes / 1048576)
            return None
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def _gifski_all_fit(self, jobs, frame_dirs, fps_arg, quality, max_bytes, work,
                        should_cancel) -> bool:
        for job, folder in zip(jobs, frame_dirs):
            _check_cancel(should_cancel)
            result = run_tool([self.gifski_path, "--fps", fps_arg, "--quality", str(quality),
                               "--repeat", "0", "-o", job.output, folder / "frame*.png"],
                              timeout=900)
            if result.returncode != 0 or not job.output.exists():
                logger.warning("gifski fallo (%s): %s", job.output.name, tail(result.stderr))
                return False
            if job.output.stat().st_size > max_bytes:
                return False
        return True

    def _encode_shared_ffmpeg(self, jobs, source_fps, max_bytes, progress_cb, should_cancel):
        ladder = [(colors, cap) for colors, cap in _FFMPEG_LADDER
                  if cap is None or cap < source_fps - 0.5]
        for colors, cap in ladder:
            fps_arg = format_fps(cap or source_fps)
            _report(progress_cb, f"FFmpeg: {fps_arg} fps, {colors} colores")
            fits = True
            for job in jobs:
                _check_cancel(should_cancel)
                graph = ",".join(f for f in (f"[0:v]fps={fps_arg}", job.filters) if f)
                graph += (f",split[a][b];[a]palettegen=max_colors={colors}:stats_mode=full"
                          f":reserve_transparent=1[p];"
                          f"[b][p]paletteuse=dither=sierra2_4a:diff_mode=rectangle")
                result = run_tool([self.ffmpeg_path, "-hide_banner", "-y", "-i", job.source,
                                   "-filter_complex", graph, "-loop", "0", job.output],
                                  timeout=900)
                if result.returncode != 0 or not job.output.exists():
                    self._last_split_error = f"FFmpeg fallo: {tail(result.stderr)}"
                    return None
                if job.output.stat().st_size > max_bytes:
                    fits = False
                    break
            if fits:
                return {"engine": "ffmpeg", "fps": fps_arg, "colors": colors}
        return None

    # ------------------------------------------------------------------
    # Still images -> JPEG parts
    # ------------------------------------------------------------------
    def _split_static(self, image: Path, preset: str, cfg: dict, out_dir: Path) -> bool:
        try:
            from PIL import Image
            with Image.open(image) as img:
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


def _check_cancel(should_cancel: CancelFn) -> None:
    if should_cancel and should_cancel():
        raise InterruptedError("Cancelado por el usuario")


def _report(progress_cb: ProgressFn, message: str) -> None:
    logger.info(message)
    if progress_cb:
        try:
            progress_cb(message)
        except Exception:  # a UI callback must never break the encoder
            pass

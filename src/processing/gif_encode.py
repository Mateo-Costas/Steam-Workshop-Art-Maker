"""processing.gif_encode - video->GIF, frames->GIF, gifsicle and the Steam trailer patch."""
import os
import tempfile
import zipfile
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from app_paths import DATA_DIR
from gif_utils import MAX_GIF_FPS, format_fps
from processing.common import logger, run_tool, tail

# Two-pass palette: build one palette for the whole clip, then dither with it.
# sierra2_4a is the best-looking error diffusion for gradients in animation.
_PALETTE_FILTER = ("split[a][b];[a]palettegen=max_colors=256:stats_mode=full[p];"
                   "[b][p]paletteuse=dither=sierra2_4a")

_GIFSICLE_URLS = (
    "https://eternallybored.org/misc/gifsicle/releases/gifsicle-1.95-win64.zip",
    "https://eternallybored.org/misc/gifsicle/releases/gifsicle-1.94-win64.zip",
)


def scale_filter(size: Optional[Tuple[int, int]] = None, max_width: Optional[int] = None) -> str:
    """ffmpeg scale expression that never distorts the image.

    size       -> cover (fill) and center-crop to exactly WxH.
    max_width  -> keep the aspect ratio, shrink to that width if wider.
    """
    if size:
        w, h = size
        return (f"scale={w}:{h}:force_original_aspect_ratio=increase:flags=lanczos,"
                f"crop={w}:{h}")
    if max_width:
        return f"scale='min(iw,{int(max_width)})':-2:flags=lanczos"
    return ""  # keep the original size


class GifEncodeMixin:
    # ------------------------------------------------------------------
    # Video -> GIF
    # ------------------------------------------------------------------
    def convert_video_to_gif(self, video_path: Path, output_path: Path, fps: float = 24,
                             start_s: Optional[float] = None, end_s: Optional[float] = None,
                             size: Optional[Tuple[int, int]] = None,
                             max_width: Optional[int] = None) -> Optional[Path]:
        """Convert any FFmpeg-readable video (or image) to an animated GIF.

        Args:
            fps: output frame rate (capped at 50, the GIF maximum).
            start_s / end_s: optional trim in seconds.
            size: (w, h) to fill-and-crop to exactly; otherwise the aspect
                ratio is kept and the width limited to ``max_width``
                (default: the Steam profile width from config).

        Returns the output path, or None on failure (details in the log).
        """
        if not self.check_ffmpeg():
            logger.error("FFmpeg no disponible para convertir video")
            return None
        fps = min(float(fps), MAX_GIF_FPS)
        if not size and not max_width:
            max_width = int(self.config.get("steam_profile.width", 638))

        cmd = [self.ffmpeg_path, "-hide_banner", "-y"]
        if start_s and start_s > 0:
            cmd += ["-ss", f"{start_s:.3f}"]  # input seek: fast and frame-accurate
        cmd += ["-i", video_path]
        if end_s and end_s > 0:
            cmd += ["-t", f"{max(0.05, end_s - (start_s or 0)):.3f}"]
        vf = f"fps={format_fps(fps)},{scale_filter(size, max_width)},{_PALETTE_FILTER}"
        cmd += ["-vf", vf, "-loop", "0", output_path]

        output_path.parent.mkdir(parents=True, exist_ok=True)
        logger.info("Convirtiendo %s -> %s (%s fps)", video_path.name, output_path.name, format_fps(fps))
        result = run_tool(cmd, timeout=900)
        if result.returncode != 0 or not output_path.exists():
            logger.error("Error convirtiendo video: %s", tail(result.stderr))
            return None
        # Intermediate file: the trailer is only patched on final fragments.
        logger.info("Video convertido: %.2f MB", output_path.stat().st_size / 1048576)
        return output_path

    # ------------------------------------------------------------------
    # Frames -> GIF
    # ------------------------------------------------------------------
    def encode_frames_to_gif(self, frame_paths: Sequence[Path], output_path: Path,
                             fps: Optional[float] = None,
                             durations_ms: Optional[Sequence[int]] = None,
                             max_width: Optional[int] = None) -> bool:
        """Encode image files (any names, same size) into one GIF with FFmpeg.

        Give either a constant ``fps`` or one duration per frame. Frame rates
        above 50 fps are resampled down so the animation keeps its real speed.
        """
        if not self.check_ffmpeg() or not frame_paths:
            return False
        if durations_ms is None:
            fps = min(float(fps or 24), 1000.0)
            durations_ms = [1000.0 / fps] * len(frame_paths)
        list_file = None
        try:
            # Concat list: one entry per frame with its own duration. Images
            # get a 1/100 s time base (the default 1/25 s would round every
            # delay to 40 ms steps).
            fd, name = tempfile.mkstemp(suffix=".ffconcat", prefix="wkart_")
            list_file = Path(name)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write("ffconcat version 1.0\n")
                for path, ms in zip(frame_paths, durations_ms):
                    safe = str(Path(path).resolve()).replace("\\", "/").replace("'", "'\\''")
                    f.write(f"file '{safe}'\noption framerate 100\n"
                            f"duration {max(ms, 1) / 1000:.4f}\n")

            real_fps = 1000.0 * len(durations_ms) / max(1.0, sum(durations_ms))
            filters = []
            if real_fps > MAX_GIF_FPS:
                # Too fast for a GIF: drop frames to 50 fps, keeping the speed.
                filters.append(f"fps={format_fps(MAX_GIF_FPS)}")
                final_delay_cs = 2
            else:
                final_delay_cs = max(2, round(durations_ms[-1] / 10))
            filters.append(scale_filter(max_width=max_width))
            filters.append(_PALETTE_FILTER)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            result = run_tool([self.ffmpeg_path, "-hide_banner", "-y",
                               "-f", "concat", "-safe", "0", "-i", list_file,
                               "-vf", ",".join(f for f in filters if f), "-fps_mode", "vfr",
                               "-final_delay", str(final_delay_cs),
                               "-loop", "0", output_path], timeout=900)
            if result.returncode != 0 or not output_path.exists():
                logger.error("Error creando GIF: %s", tail(result.stderr))
                return False
            return True
        except OSError as e:
            logger.error("Error creando GIF: %s", e)
            return False
        finally:
            if list_file is not None:
                list_file.unlink(missing_ok=True)

    def create_optimized_gif(self, frame_paths: List[Path], output_path: Path, fps: float,
                             max_width: Optional[int] = None) -> bool:
        """Assemble processed frames (AI upscale, RIFE) into an intermediate GIF.

        The aspect ratio is kept; the width is limited to the Steam profile
        width so the file stays manageable for the next steps.
        """
        valid = [p for p in frame_paths if Path(p).exists()]
        if not valid:
            logger.error("No hay frames validos para crear el GIF")
            return False
        if max_width is None:
            max_width = int(self.config.get("steam_profile.width", 638))
        if not self.encode_frames_to_gif(valid, output_path, fps=fps, max_width=max_width):
            return False
        self._try_gifsicle_optimize(output_path)
        logger.info("GIF creado: %s (%.2f MB)", output_path.name,
                    output_path.stat().st_size / 1048576)
        return True

    # ------------------------------------------------------------------
    # gifsicle (lossless LZW recompression of intermediate GIFs)
    # ------------------------------------------------------------------
    def _download_gifsicle(self) -> Optional[Path]:
        """Download gifsicle.exe into SteamWorkshopAppData/ (once per session)."""
        if self._gifsicle_unavailable or os.name != "nt":
            return None
        dest = DATA_DIR / "gifsicle.exe"
        if dest.exists():
            return dest
        import requests
        for url in _GIFSICLE_URLS:
            tmp = None
            try:
                resp = requests.get(url, stream=True, timeout=30)
                resp.raise_for_status()
                fd, name = tempfile.mkstemp(suffix=".zip")
                tmp = Path(name)
                with os.fdopen(fd, "wb") as f:
                    for chunk in resp.iter_content(65536):
                        f.write(chunk)
                with zipfile.ZipFile(tmp) as zf:
                    member = next((n for n in zf.namelist()
                                   if n.lower().endswith("gifsicle.exe")), None)
                    if member:
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        dest.write_bytes(zf.read(member))
                if dest.exists():
                    logger.info("gifsicle descargado: %s", dest)
                    return dest
            except Exception as e:  # network/zip errors: try the next mirror
                logger.warning("No se pudo descargar gifsicle (%s): %s", url, e)
            finally:
                if tmp is not None:
                    tmp.unlink(missing_ok=True)
        self._gifsicle_unavailable = True
        return None

    def _try_gifsicle_optimize(self, gif_path: Path) -> None:
        """Run gifsicle --optimize=3 in place; keep the result only if smaller."""
        exe = self.gifsicle_path if self.gifsicle_path and self.gifsicle_path.exists() else None
        exe = exe or self._download_gifsicle()
        if not exe:
            return
        self.gifsicle_path = exe
        out = gif_path.with_name(gif_path.stem + "_gs.gif")
        result = run_tool([exe, "--optimize=3", "-o", out, gif_path], timeout=180)
        try:
            if result.returncode == 0 and out.exists() and out.stat().st_size < gif_path.stat().st_size:
                before = gif_path.stat().st_size
                out.replace(gif_path)
                logger.info("gifsicle: %.2f -> %.2f MB", before / 1048576,
                            gif_path.stat().st_size / 1048576)
        finally:
            out.unlink(missing_ok=True)

    # ------------------------------------------------------------------
    # Steam trailer patch
    # ------------------------------------------------------------------
    def _patch_gif_trailer(self, path: Path) -> bool:
        """Replace the final 0x3B trailer with 0x21 so Steam shows the GIF full size.

        Only final fragments are patched: Pillow cannot read patched files, so
        intermediate GIFs keep a valid trailer (see gif_utils.open_gif).
        """
        if not self.patch_trailer_for_steam or not path or not path.exists():
            return False
        try:
            with open(path, "r+b") as f:
                f.seek(-1, os.SEEK_END)
                if f.read(1) != b"\x3B":
                    return False
                f.seek(-1, os.SEEK_END)
                f.write(b"\x21")
            return True
        except OSError as e:
            logger.warning("No se pudo parchear %s: %s", path.name, e)
            return False

"""processing.frames - frame extraction and AI upscaling (Real-ESRGAN / Real-CUGAN)."""
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from PIL import Image

from gif_utils import format_fps, playback_fps
from processing.common import _NO_WINDOW_FLAGS, logger, run_tool, tail
from video_utils import is_video, probe_video

# Model table of the optional realesrgan-ncnn-py bindings (package model ids).
# Other models (realesrnet, general-v3, CUGAN, user models) use the CLI.
_BINDING_MODEL_IDS = {
    "realesr-animevideov3-x2": 0,
    "realesr-animevideov3-x3": 1,
    "realesr-animevideov3-x4": 2,
    "realesrgan-x4plus-anime": 3,
    "realesrgan-x4plus": 4,
}


class FramesMixin:
    def extract_gif_frames(self, source: Path, output_dir: Path, max_fps: float = 50.0,
                           max_width: Optional[int] = None
                           ) -> Tuple[Optional[List[Path]], Optional[float]]:
        """Extract the frames of a GIF (or video) as PNGs at a constant rate.

        The rate reproduces the source speed (see gif_utils.playback_fps), so
        re-encoding the frames at the returned fps keeps the original timing.
        ``max_width`` shrinks wider sources (aspect ratio kept).
        Returns (sorted frame paths, fps) or (None, None) on failure.
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        try:
            if is_video(source):
                fps = probe_video(source).fps or 24.0
            else:
                fps = playback_fps(source)
        except (OSError, ValueError) as e:
            logger.error("No se pudo leer %s: %s", source.name, e)
            return None, None
        fps = min(fps, max_fps)
        filters = f"fps={format_fps(fps)}"
        if max_width:
            filters += f",scale='min(iw,{int(max_width)})':-2:flags=lanczos"
        result = run_tool([self.ffmpeg_path, "-hide_banner", "-y", "-i", source,
                           "-vf", filters, output_dir / "frame_%06d.png"], timeout=900)
        frames = sorted(output_dir.glob("frame_*.png"))
        if result.returncode != 0 or not frames:
            logger.error("Error extrayendo frames: %s", tail(result.stderr))
            return None, None
        return frames, fps

    def upscale_frames_batch(self, input_dir: Path, output_dir: Path,
                             model_name: str = "realesrgan-x4plus",
                             use_gpu: bool = True,
                             progress_callback: Optional[Callable] = None) -> Optional[List[Path]]:
        """Upscale every PNG in input_dir with Real-ESRGAN or Real-CUGAN.

        Uses the realesrgan-ncnn-py bindings when installed and the model is
        one of theirs, otherwise the ncnn-vulkan command-line tool. A GPU
        failure is retried once on the CPU. Returns the sorted output frames.
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        input_frames = sorted(input_dir.glob("*.png"))
        if not input_frames:
            _progress(progress_callback, "Error: no hay frames de entrada", 0)
            return None

        # The UI may pass "model_id - description"; keep the id only.
        model = model_name.split(" - ")[0].strip()
        info = self.model_manager.get_model_info(model)
        engine = info.get("engine", "realesrgan")

        if engine == "realesrgan" and model in _BINDING_MODEL_IDS:
            upscaled = self._upscale_with_bindings(input_frames, output_dir, model,
                                                   use_gpu, progress_callback)
            if upscaled:
                return upscaled

        if engine == "realcugan":
            exe = self.realcugan_path
            cugan = info.get("cugan_args", {})
            args = ["-s", str(cugan.get("scale", 2)), "-n", str(cugan.get("noise", 0)),
                    "-m", self.model_manager.cugan_models_dir(cugan.get("model_dir", "models-se"))]
        else:
            exe = self.realesrgan_path
            # -s must match the model's native scale: an x2 model run with -s 4
            # produces a scrambled image.
            args = ["-n", model, "-s", str(self.model_manager.model_scale(model)),
                    "-m", self.model_manager.models_dir]
        if not exe or not Path(exe).exists():
            tool = "Real-CUGAN" if engine == "realcugan" else "Real-ESRGAN"
            _progress(progress_callback, f"Error: {tool} no encontrado", 0)
            return None
        cmd = [exe, *args, "-i", input_dir, "-o", output_dir, "-f", "png",
               "-g", "0" if use_gpu else "-1"]

        ok, stderr = self._run_upscaler(cmd, len(input_frames), output_dir, use_gpu,
                                        progress_callback)
        upscaled = sorted(output_dir.glob("*.png"))
        if ok and upscaled:
            _progress(progress_callback, f"IA completada: {len(upscaled)} frames", 80)
            return upscaled
        if use_gpu:
            logger.warning("Fallo con GPU (%s), reintentando con CPU", tail(stderr, 200))
            _progress(progress_callback, "Error con la GPU, reintentando con CPU...", 20)
            for leftover in upscaled:
                leftover.unlink(missing_ok=True)
            return self.upscale_frames_batch(input_dir, output_dir, model, use_gpu=False,
                                             progress_callback=progress_callback)
        _progress(progress_callback, f"Error en el procesamiento con IA: {tail(stderr, 200)}", 0)
        return None

    def _upscale_with_bindings(self, frames, output_dir, model, use_gpu, progress_callback):
        try:
            from realesrgan_ncnn_py import Realesrgan
        except ImportError:
            return None  # optional dependency
        try:
            upscaler = Realesrgan(gpuid=0 if use_gpu else -1, model=_BINDING_MODEL_IDS[model])
            out = []
            for index, frame in enumerate(frames, 1):
                with Image.open(frame) as image:
                    upscaler.process_pil(image).save(output_dir / frame.name)
                out.append(output_dir / frame.name)
                _progress(progress_callback, f"IA: frame {index}/{len(frames)}",
                          20 + int(index / len(frames) * 60))
            logger.info("Upscale con realesrgan-ncnn-py: %d frames", len(out))
            return out
        except Exception as e:  # bindings failure: fall back to the CLI
            logger.warning("realesrgan-ncnn-py fallo (%s), usando el ejecutable", e)
            return None

    def _run_upscaler(self, cmd, total, output_dir, use_gpu, progress_callback):
        """Run an ncnn-vulkan upscaler, reporting progress by counting output files."""
        mode = "GPU" if use_gpu else "CPU"
        _progress(progress_callback, f"Iniciando IA con {mode}...", 20)
        logger.info("Ejecutando: %s", " ".join(str(c) for c in cmd))
        process = subprocess.Popen([str(c) for c in cmd], stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True, encoding="utf-8",
                                   errors="replace", cwd=str(Path(cmd[0]).parent),
                                   **_NO_WINDOW_FLAGS)
        stop = threading.Event()
        started = time.time()

        def watch():
            last = -1
            while not stop.wait(2.0):
                done = sum(1 for _ in output_dir.glob("*.png"))
                if done != last:
                    last = done
                    rate = done / max(0.001, time.time() - started)
                    eta = int((total - done) / rate) if rate > 0.01 else 0
                    _progress(progress_callback,
                              f"IA: {done}/{total} frames ({rate:.2f} f/s, ETA {eta}s)",
                              20 + int(done / max(1, total) * 60))

        watcher = threading.Thread(target=watch, daemon=True)
        watcher.start()
        # Generous timeout: 10 min base + 5 s per frame (CPU mode is slow).
        timeout = max(600, 300 + 5 * total)
        try:
            _, stderr = process.communicate(timeout=timeout)
            return process.returncode == 0, stderr or ""
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate()
            return False, f"timeout tras {timeout} s"
        finally:
            stop.set()


def _progress(callback, message: str, percent: float) -> None:
    logger.info(message)
    if callback:
        try:
            callback(message, percent)
        except Exception:  # never let a UI callback break the upscale
            pass

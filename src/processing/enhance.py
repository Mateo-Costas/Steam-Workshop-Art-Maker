"""processing.enhance - color adjustments (contrast, saturation, vibrance, sharpness, temperature)."""
import math
import os
import shutil
import tempfile
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageSequence

from gif_utils import DEFAULT_DELAY_MS, MIN_DELAY_MS, open_image
from processing.common import CancelFn, check_cancel, logger

#: Neutral values of the sliders: an adjustment at its neutral value is skipped.
NEUTRAL_COLORS = {"contrast": 1.0, "saturation": 1.0, "vibrance": 0.0,
                  "sharpness": 0.0, "temperature": 0.0}
#: Range of each slider in step 2 (values outside are clamped).
COLOR_RANGES = {"contrast": (0.5, 2.0), "saturation": (0.5, 2.0), "vibrance": (0.0, 1.0),
                "sharpness": (0.0, 1.0), "temperature": (-1.0, 1.0)}
#: Values the sliders start with ("vivid" style).
DEFAULT_COLORS = {"contrast": 1.5, "saturation": 1.3, "vibrance": 0.0,
                  "sharpness": 0.0, "temperature": 0.0}
#: One-click looks for the sliders, in display order.
COLOR_PRESETS = {
    "original": NEUTRAL_COLORS,
    "soft": {"contrast": 1.15, "saturation": 1.1, "vibrance": 0.2,
             "sharpness": 0.1, "temperature": 0.0},
    "vivid": DEFAULT_COLORS,
    "intense": {"contrast": 1.7, "saturation": 1.5, "vibrance": 0.4,
                "sharpness": 0.3, "temperature": 0.0},
    "warm": {"contrast": 1.25, "saturation": 1.2, "vibrance": 0.2,
             "sharpness": 0.1, "temperature": 0.35},
    "cool": {"contrast": 1.25, "saturation": 1.15, "vibrance": 0.2,
             "sharpness": 0.1, "temperature": -0.35},
}


def clamp_colors(values: dict) -> dict:
    """Valid slider values from a (possibly hand-edited) config entry."""
    out = {}
    for name, (low, high) in COLOR_RANGES.items():
        try:
            value = float(values.get(name, DEFAULT_COLORS[name]))
        except (TypeError, ValueError, AttributeError):
            value = DEFAULT_COLORS[name]
        out[name] = min(high, max(low, value)) if math.isfinite(value) else DEFAULT_COLORS[name]
    return out
#: Frames adjusted in parallel (Pillow and NumPy release the GIL while they work).
_WORKERS = max(1, min(4, (os.cpu_count() or 2) - 1))


class EnhanceMixin:
    # ------------------------------------------------------------------
    # Per-frame color operations (also used by the live color preview)
    # ------------------------------------------------------------------
    @staticmethod
    def _apply_vibrance(img: Image.Image, amount: float) -> Image.Image:
        """Boost under-saturated pixels more than already-vivid ones (amount 0..1).
        Unlike uniform saturation, vibrance protects already-vivid colours from clipping."""
        if amount == 0:
            return img
        arr = np.array(img.convert("RGB"), dtype=np.float32) / 255.0
        r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]
        mx = np.maximum(np.maximum(r, g), b)
        mn = np.minimum(np.minimum(r, g), b)
        sat = (mx - mn) / np.maximum(mx, 1e-6)        # per-pixel HSV saturation, 0..1
        boost = 1.0 + amount * (1.0 - sat)            # low-saturation pixels receive a larger multiplier
        gray = mx[:, :, np.newaxis]                    # use max channel as neutral reference
        out = arr + (arr - gray) * (boost[:, :, np.newaxis] - 1.0)
        return Image.fromarray((np.clip(out, 0, 1) * 255).astype(np.uint8))

    @staticmethod
    def _apply_sharpness(img: Image.Image, amount: float) -> Image.Image:
        """Unsharp mask sharpening (amount 0..1 maps to 0-200% strength).
        radius=1.2 and threshold=2 are tuned to avoid haloing on GIF frames."""
        if amount == 0:
            return img
        return img.filter(ImageFilter.UnsharpMask(
            radius=1.2, percent=int(amount * 200), threshold=2))

    @staticmethod
    def _apply_temperature(img: Image.Image, amount: float) -> Image.Image:
        """Warm (+) / cool (-) color temperature shift (amount -1..+1).
        Shifts red channel up and blue channel down for warmth (opposite for cool).
        Max delta of +-30 keeps the effect subtle enough for typical art use."""
        if amount == 0:
            return img
        r, g, b = img.convert("RGB").split()

        def _shift(channel, delta):
            # int16 avoids uint8 wrap-around before clamp
            arr = np.array(channel, dtype=np.int16) + delta
            return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))

        delta = int(amount * 30)
        return Image.merge("RGB", (_shift(r, delta), g, _shift(b, -delta)))

    def apply_color_adjustments(self, frame: Image.Image, contrast: float, saturation: float,
                                vibrance: float = 0.0, sharpness: float = 0.0,
                                temperature: float = 0.0) -> Image.Image:
        """Apply every color adjustment to one RGB frame, in the app's fixed order."""
        frame = frame.convert("RGB")
        if 0.5 <= contrast <= 3.0 and abs(contrast - 1.0) > 0.005:
            frame = ImageEnhance.Contrast(frame).enhance(contrast)
        if 0.5 <= saturation <= 3.0 and abs(saturation - 1.0) > 0.005:
            frame = ImageEnhance.Color(frame).enhance(saturation)
        if vibrance > 0.01:
            frame = self._apply_vibrance(frame, vibrance)
        if sharpness > 0.01:
            frame = self._apply_sharpness(frame, sharpness)
        if abs(temperature) > 0.01:
            frame = self._apply_temperature(frame, temperature)
        return frame

    # ------------------------------------------------------------------
    # File-level enhancement
    # ------------------------------------------------------------------
    def enhance_colors(self, image_path: Path, contrast: float = 1.5,
                       saturation: float = 1.3, vibrance: float = 0.0,
                       sharpness: float = 0.0, temperature: float = 0.0,
                       should_cancel: CancelFn = None) -> Path:
        """Apply the color adjustments to an image or an animated GIF.

        GIFs keep the exact delay of every frame. The result is written to the
        workspace "mejorado" folder; if anything fails the original path is
        returned (and the reason logged). Raises InterruptedError on cancel.
        """
        out_dir = self._workspace_dir(image_path, "mejorado")
        out_name = f"{image_path.stem}_enhanced{image_path.suffix.lower()}"
        self._archive_before_overwrite(out_dir, keep_names=[out_name], protect=image_path)
        output_path = out_dir / out_name
        adjust = dict(contrast=contrast, saturation=saturation, vibrance=vibrance,
                      sharpness=sharpness, temperature=temperature)
        logger.info("Mejorando colores de %s: %s", image_path.name, adjust)

        try:
            with open_image(image_path) as img:
                animated = getattr(img, "n_frames", 1) > 1
                if animated:
                    ok = self._enhance_animation(img, output_path, adjust, should_cancel)
                else:
                    result = self.apply_color_adjustments(img, **adjust)
                    save_args = {"quality": 95} if output_path.suffix in (".jpg", ".jpeg") else {}
                    result.save(output_path, **save_args)
                    ok = output_path.exists()
            if not ok or output_path.stat().st_size == 0:
                raise RuntimeError("no se genero el archivo mejorado")
        except InterruptedError:
            output_path.unlink(missing_ok=True)
            raise
        except Exception as e:
            logger.error("Error mejorando colores: %s", e)
            output_path.unlink(missing_ok=True)
            return image_path

        self._write_manifest(out_dir, "mejorar_colores", adjust,
                             archivos=[output_path], fuente=image_path)
        logger.info("Colores mejorados: %.2f MB", output_path.stat().st_size / 1048576)
        return output_path

    def _adjust_and_save(self, frame: Image.Image, path: Path, adjust: dict) -> None:
        self.apply_color_adjustments(frame, **adjust).save(path, compress_level=1)

    def _enhance_animation(self, img: Image.Image, output_path: Path, adjust: dict,
                           should_cancel: CancelFn = None) -> bool:
        """Adjust every frame, keep each frame's delay, re-encode with a global palette.

        GIF frames must be decoded in order, but adjusting and saving them is
        independent work: it runs on a small thread pool while the next
        frames are decoded (at most 2 frames per worker wait in memory).
        """
        work = Path(tempfile.mkdtemp(prefix="wkart_enh_"))
        try:
            frames, durations = [], []
            with ThreadPoolExecutor(max_workers=_WORKERS) as pool:
                pending = deque()
                for index, frame in enumerate(ImageSequence.Iterator(img)):
                    check_cancel(should_cancel)
                    delay = int(frame.info.get("duration") or 0)
                    durations.append(delay if delay >= MIN_DELAY_MS else DEFAULT_DELAY_MS)
                    path = work / f"f{index:06d}.png"
                    # convert() copies the frame: the iterator reuses its buffer.
                    pending.append(pool.submit(self._adjust_and_save, frame.convert("RGBA"),
                                               path, adjust))
                    frames.append(path)
                    while len(pending) > 2 * _WORKERS:
                        pending.popleft().result()
                for job in pending:
                    job.result()
            return self.encode_frames_to_gif(frames, output_path, durations_ms=durations,
                                             should_cancel=should_cancel)
        finally:
            shutil.rmtree(work, ignore_errors=True)

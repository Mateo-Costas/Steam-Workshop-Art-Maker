"""processing.enhance - color adjustments (contrast, saturation, vibrance, sharpness, temperature)."""
import shutil
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageSequence

from gif_utils import DEFAULT_DELAY_MS, MIN_DELAY_MS, open_image
from processing.common import logger


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
        if 0.5 <= contrast <= 3.0:
            frame = ImageEnhance.Contrast(frame).enhance(contrast)
        if 0.5 <= saturation <= 3.0:
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
                       sharpness: float = 0.0, temperature: float = 0.0) -> Path:
        """Apply the color adjustments to an image or an animated GIF.

        GIFs keep the exact delay of every frame. The result is written to the
        workspace "mejorado" folder; if anything fails the original path is
        returned (and the reason logged).
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
                    ok = self._enhance_animation(img, output_path, adjust)
                else:
                    result = self.apply_color_adjustments(img, **adjust)
                    save_args = {"quality": 95} if output_path.suffix in (".jpg", ".jpeg") else {}
                    result.save(output_path, **save_args)
                    ok = output_path.exists()
            if not ok or output_path.stat().st_size == 0:
                raise RuntimeError("no se genero el archivo mejorado")
        except Exception as e:
            logger.error("Error mejorando colores: %s", e)
            output_path.unlink(missing_ok=True)
            return image_path

        self._write_manifest(out_dir, "mejorar_colores", adjust,
                             archivos=[output_path], fuente=image_path)
        logger.info("Colores mejorados: %.2f MB", output_path.stat().st_size / 1048576)
        return output_path

    def _enhance_animation(self, img: Image.Image, output_path: Path, adjust: dict) -> bool:
        """Adjust every frame, keep each frame's delay, re-encode with a global palette."""
        work = Path(tempfile.mkdtemp(prefix="wkart_enh_"))
        try:
            frames, durations = [], []
            for index, frame in enumerate(ImageSequence.Iterator(img)):
                delay = int(frame.info.get("duration") or 0)
                durations.append(delay if delay >= MIN_DELAY_MS else DEFAULT_DELAY_MS)
                path = work / f"f{index:06d}.png"
                self.apply_color_adjustments(frame.convert("RGBA"), **adjust).save(
                    path, compress_level=1)
                frames.append(path)
            return self.encode_frames_to_gif(frames, output_path, durations_ms=durations)
        finally:
            shutil.rmtree(work, ignore_errors=True)

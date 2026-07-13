"""
analyzers.py - Computer-vision content analyzer for automatic AI model selection.

Inspects a GIF, image, or video and classifies it as one of:
  anime, gaming, realistic, or mixed.

The classification drives which upscaling model is recommended (see ModelManager).

Feature set (per frame) - chosen because each one genuinely separates the
classes, unlike the previous HSV-range heuristics that classified almost
everything as anime:

  flat_ratio    - fraction of 16x16 blocks with near-zero color variance.
                  Cel-shaded anime is full of flat fills; photos have sensor
                  noise and gradients everywhere, so their blocks never
                  measure as flat.
  palette_conc  - coverage of the top-16 colors after quantizing to 32
                  levels per channel. Anime concentrates into few colors;
                  photos and dithered GIFs spread widely. Quantizing makes
                  this robust to GIF palettes (a photo saved as GIF still
                  spreads across hundreds of quantized bins).
  dark_lines    - fraction of Canny edge pixels that are also dark
                  (luminance < 80): anime outlines are drawn in near-black.
  noise_level   - mean absolute residual after a median filter. Photos have
                  moderate sensor noise; anime is near zero; pure noise is
                  extreme (which is how noise avoids the realistic class).
  rect_score    - count of large rectangular contours (game HUD elements).

Decision order: anime -> gaming -> realistic -> mixed, with thresholds
calibrated against a labeled synthetic bench (anime/photo/gaming/noise, each
also in GIF-palette form).
"""

import logging
from pathlib import Path
from typing import Any, Dict, List

import cv2
import numpy as np
from PIL import Image

logger = logging.getLogger("WorkshopArtPRO.analyzers")

#: Longest image side used for analysis; larger inputs are downscaled first.
_ANALYSIS_MAX_SIDE = 512


class ContentAnalyzer:
    """Static-method-only analyzer. No instance state; all methods are @staticmethod."""

    # Decision thresholds (calibrated on the synthetic bench, see module docstring).
    _ANIME_THRESHOLD = 0.45
    _GAMING_THRESHOLD = 0.45
    _NOISE_PHOTO_RANGE = (0.010, 0.120)  # median-residual band typical of photos

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    @staticmethod
    def analyze_content(file_path: Path) -> Dict[str, Any]:
        """Analyze a file and return a classification dict.

        For GIFs, samples up to 5 frames spread across the animation; for
        videos, up to 3 frames spaced ~1 s apart. Scores are averaged before
        the final decision. Always appends 'aspect_ratio' and
        'upload_suggestion' (Steam format hint).
        """
        results = ContentAnalyzer._empty_result()
        _aw = _ah = 0
        try:
            suffix = file_path.suffix.lower()
            frames: List[Image.Image] = []

            if suffix == ".gif":
                with Image.open(file_path) as img:
                    _aw, _ah = img.size
                    total = getattr(img, "n_frames", 1)
                    # Spread samples across the clip; the first frames of a
                    # GIF are often an intro/fade and misrepresent it.
                    indices = sorted({int(total * f) for f in
                                      (0.1, 0.3, 0.5, 0.7, 0.9)} & set(range(total)))
                    for index in indices or [0]:
                        try:
                            img.seek(index)
                            frames.append(img.convert("RGB"))
                        except Exception:
                            break

            elif suffix in (".jpg", ".jpeg", ".png", ".bmp", ".webp"):
                with Image.open(file_path) as img:
                    _aw, _ah = img.size
                    frames.append(img.convert("RGB"))

            elif suffix in (".mp4", ".avi", ".mov", ".mkv", ".webm"):
                cap = cv2.VideoCapture(str(file_path))
                _aw = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                _ah = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                grabbed, count = 0, 0
                while grabbed < 3:
                    ok, frame = cap.read()
                    if not ok:
                        break
                    if count % 30 == 0:  # ~1 frame per second at 30 fps
                        frames.append(Image.fromarray(
                            cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)))
                        grabbed += 1
                    count += 1
                cap.release()

            if frames:
                per_frame = [ContentAnalyzer._score_frame(f) for f in frames]
                results = ContentAnalyzer._combine(per_frame)

        except Exception as e:
            logger.warning("Error analizando contenido: %s", e)

        if _aw > 0 and _ah > 0:
            results["aspect_ratio"] = round(_aw / _ah, 3)
            results["upload_suggestion"] = \
                ContentAnalyzer._get_upload_suggestion(_aw, _ah)

        logger.debug(
            "Analisis: anime=%.2f gaming=%.2f realistic=%.2f tipo=%s "
            "confianza=%.0f%% modelo=%s",
            results["anime_score"], results["gaming_score"],
            results["realistic_score"], results["type"],
            results["confidence"] * 100, results["recommended_model"])
        return results

    # ------------------------------------------------------------------
    # Per-frame feature extraction
    # ------------------------------------------------------------------
    @staticmethod
    def _score_frame(img: Image.Image) -> Dict[str, float]:
        """Compute the raw feature values for one RGB frame."""
        arr = np.asarray(img)
        if arr.ndim == 2:
            arr = cv2.cvtColor(arr, cv2.COLOR_GRAY2RGB)
        elif arr.shape[2] == 4:
            arr = cv2.cvtColor(arr, cv2.COLOR_RGBA2RGB)

        # Downscale: keeps every metric O(512^2) and scale-independent.
        h, w = arr.shape[:2]
        if max(h, w) > _ANALYSIS_MAX_SIDE:
            scale = _ANALYSIS_MAX_SIDE / max(h, w)
            arr = cv2.resize(arr, (int(w * scale), int(h * scale)),
                             interpolation=cv2.INTER_AREA)

        gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
        return {
            "flat_ratio": ContentAnalyzer._flat_ratio(arr),
            "palette_conc": ContentAnalyzer._palette_concentration(arr),
            "dark_lines": ContentAnalyzer._dark_line_ratio(gray),
            "noise_level": ContentAnalyzer._noise_level(gray),
            "rect_score": ContentAnalyzer._rect_score(gray),
        }

    @staticmethod
    def _flat_ratio(arr: np.ndarray) -> float:
        """Fraction of 16x16 blocks whose color variance is near zero.

        Vectorized: reshape into a block grid and compute per-block variance
        in one pass instead of a Python loop.
        """
        block = 16
        h, w = arr.shape[:2]
        bh, bw = h // block, w // block
        if bh == 0 or bw == 0:
            return 0.0
        cropped = arr[: bh * block, : bw * block].astype(np.float32)
        blocks = cropped.reshape(bh, block, bw, block, 3).transpose(0, 2, 1, 3, 4)
        variances = blocks.reshape(bh, bw, -1).var(axis=2)
        return float((variances < 30.0).mean())

    @staticmethod
    def _palette_concentration(arr: np.ndarray) -> float:
        """Coverage of the 16 most frequent colors after 32-level quantization."""
        q = (arr >> 3).reshape(-1, 3)
        # Pack the three 5-bit channels into one int for a fast bincount.
        packed = (q[:, 0].astype(np.int32) << 10) | \
                 (q[:, 1].astype(np.int32) << 5) | q[:, 2].astype(np.int32)
        counts = np.bincount(packed, minlength=1 << 15)
        top16 = np.sort(counts)[-16:].sum()
        return float(top16 / packed.size)

    @staticmethod
    def _dark_line_ratio(gray: np.ndarray) -> float:
        """Fraction of Canny edge pixels that are also dark (drawn outlines)."""
        edges = cv2.Canny(gray, 50, 150)
        edge_count = int((edges > 0).sum())
        if edge_count < 50:
            return 0.0
        dark_edges = int(((edges > 0) & (gray < 80)).sum())
        return dark_edges / edge_count

    @staticmethod
    def _noise_level(gray: np.ndarray) -> float:
        """Mean absolute residual after a 3x3 median filter, normalized 0..1."""
        median = cv2.medianBlur(gray, 3)
        return float(np.mean(np.abs(gray.astype(np.float32) -
                                    median.astype(np.float32))) / 255.0)

    @staticmethod
    def _rect_score(gray: np.ndarray) -> float:
        """Normalized count of large rectangular contours (HUD/UI elements)."""
        edges = cv2.Canny(gray, 50, 150)
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL,
                                       cv2.CHAIN_APPROX_SIMPLE)
        rectangles = 0
        for contour in contours:
            if cv2.contourArea(contour) > 400:
                perimeter = cv2.arcLength(contour, True)
                approx = cv2.approxPolyDP(contour, 0.02 * perimeter, True)
                if len(approx) == 4:
                    rectangles += 1
        return min(1.0, rectangles / 5.0)

    # ------------------------------------------------------------------
    # Decision
    # ------------------------------------------------------------------
    @staticmethod
    def _combine(per_frame: List[Dict[str, float]]) -> Dict[str, Any]:
        """Average per-frame features and map them to a classification."""
        f = {key: float(np.mean([s[key] for s in per_frame]))
             for key in per_frame[0]}

        # Anime: flat fills + concentrated palette + dark outlines, no noise.
        anime_score = (0.40 * f["flat_ratio"]
                       + 0.35 * f["palette_conc"]
                       + 0.25 * min(1.0, f["dark_lines"] * 2.5))
        if f["noise_level"] > 0.05:
            # Sensor noise this high never happens in clean anime frames.
            anime_score *= 0.4

        gaming_score = f["rect_score"]
        if f["flat_ratio"] < 0.01:
            # Real HUDs are flat-filled panels, so a frame with zero flat
            # blocks (e.g. pure noise) can't be a game screenshot even if
            # spurious rectangular contours show up.
            gaming_score *= 0.3

        lo, hi = ContentAnalyzer._NOISE_PHOTO_RANGE
        photo_noise = lo <= f["noise_level"] <= hi
        realistic_score = ((0.6 if photo_noise else 0.0)
                           + 0.4 * (1.0 - min(1.0, f["palette_conc"] * 2.5)))

        if anime_score >= ContentAnalyzer._ANIME_THRESHOLD:
            content_type, model = "anime", "realesr-animevideov3-x4"
            confidence = anime_score
        elif gaming_score >= ContentAnalyzer._GAMING_THRESHOLD:
            content_type, model = "gaming", "realesrgan-x4plus"
            confidence = gaming_score
        elif realistic_score >= 0.5:
            content_type, model = "realistic", "realesrnet-x4plus"
            confidence = realistic_score
        else:
            content_type, model = "mixed", "realesrgan-x4plus"
            confidence = 0.5

        result = ContentAnalyzer._empty_result()
        result.update({
            "type": content_type,
            "recommended_model": model,
            "confidence": round(min(1.0, confidence), 3),
            "characteristics": [content_type],
            "anime_score": round(anime_score, 3),
            "gaming_score": round(gaming_score, 3),
            "realistic_score": round(realistic_score, 3),
            "details": {
                "frames_analyzed": len(per_frame),
                **{key: round(value, 4) for key, value in f.items()},
            },
        })
        return result

    @staticmethod
    def _empty_result() -> Dict[str, Any]:
        return {
            "type": "unknown",
            "characteristics": [],
            "recommended_model": "realesrgan-x4plus",
            "confidence": 0.0,
            "details": {},
            "anime_score": 0.0,
            "gaming_score": 0.0,
            "realistic_score": 0.0,
            "aspect_ratio": None,
            "upload_suggestion": None,
        }

    # ------------------------------------------------------------------
    # Steam format suggestion (unchanged public helper)
    # ------------------------------------------------------------------
    @staticmethod
    def _get_upload_suggestion(w: int, h: int) -> str:
        """Map image dimensions to the recommended Steam Workshop display format.

        Thresholds are based on Steam's actual aspect-ratio ranges:
        >= 3.5  -> Workshop Showcase (5-part banner 638x354)
        >= 1.5  -> Screenshot Showcase
        >= 0.8  -> Artwork Showcase (main 506px + side 100px)
        < 0.8   -> Artwork Showcase or Profile Background
        """
        if h <= 0:
            return "Artwork Showcase"
        ratio = w / h
        if ratio >= 3.5:
            return "Workshop Showcase (5 partes 638x354)"
        elif ratio >= 1.5:
            return "Screenshot Showcase (638x354)"
        elif ratio >= 0.8:
            return "Artwork Showcase (main 506px + side 100px)"
        else:
            return "Artwork Showcase o Perfil Background"

    @staticmethod
    def get_content_description(content_type: str) -> str:
        """Human-readable description of a detected content type."""
        descriptions = {
            "anime": "Anime — dibujo/animación (mejor: realesr-animevideov3-x4)",
            "gaming": "Gaming — capturas de videojuegos, UI/HUD visible",
            "realistic": "Realista/Foto — fotografía o render 3D fotorrealista",
            "mixed": "Mixto — contenido variado sin tipo dominante",
        }
        return descriptions.get(content_type, "Tipo desconocido")

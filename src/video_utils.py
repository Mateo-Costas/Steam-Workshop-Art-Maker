"""video_utils - lightweight video probing and thumbnail sampling (OpenCV).

Replaces the former moviepy dependency: OpenCV is already required by the
app and its bundled FFmpeg backend reads every container the UI accepts.
"""
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional, Tuple

import cv2
from PIL import Image

#: Extensions the app treats as video (file picker, drag & drop, converters).
VIDEO_EXTS = frozenset({".mp4", ".avi", ".mov", ".mkv", ".webm", ".m4v", ".flv"})
#: Static image formats accepted as input.
IMAGE_EXTS = frozenset({".jpg", ".jpeg", ".png", ".bmp", ".webp"})
#: Everything the app can open.
MEDIA_EXTS = VIDEO_EXTS | IMAGE_EXTS | {".gif"}


@dataclass
class VideoInfo:
    width: int
    height: int
    fps: float
    frames: int

    @property
    def duration(self) -> float:
        """Duration in seconds (0 when the container doesn't report it)."""
        return self.frames / self.fps if self.fps > 0 else 0.0


def is_video(path: Path) -> bool:
    return Path(path).suffix.lower() in VIDEO_EXTS


def probe_video(path: Path) -> VideoInfo:
    """Read size, frame rate and frame count. Raises ValueError if unreadable."""
    cap = cv2.VideoCapture(str(path))
    try:
        if not cap.isOpened():
            raise ValueError(f"No se pudo abrir el video: {Path(path).name}")
        info = VideoInfo(
            width=int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
            height=int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
            fps=float(cap.get(cv2.CAP_PROP_FPS) or 0.0),
            frames=int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0),
        )
    finally:
        cap.release()
    if info.width <= 0 or info.height <= 0:
        raise ValueError(f"Video sin dimensiones legibles: {Path(path).name}")
    return info


def sample_frames(path: Path, max_frames: int, thumb_size: Tuple[int, int],
                  should_stop: Optional[Callable[[], bool]] = None
                  ) -> Tuple[List[Image.Image], int]:
    """Decode up to ``max_frames`` evenly spaced thumbnails covering the whole video.

    Returns (RGBA thumbnails, delay between them in ms). ``should_stop`` is
    polled so a caller can abandon a preview that is no longer needed.
    """
    info = probe_video(path)
    step = max(1, math.ceil(info.frames / max_frames)) if info.frames else 1
    fps = info.fps if info.fps > 0 else 25.0
    delay_ms = max(20, int(round(1000.0 * step / fps)))

    frames: List[Image.Image] = []
    cap = cv2.VideoCapture(str(path))
    try:
        index = 0
        while len(frames) < max_frames:
            if should_stop and should_stop():
                return [], delay_ms
            if index % step:
                if not cap.grab():
                    break
            else:
                ok, bgr = cap.read()
                if not ok:
                    break
                image = Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
                image.thumbnail(thumb_size, Image.Resampling.LANCZOS)
                frames.append(image.convert("RGBA"))
            index += 1
    finally:
        cap.release()
    return frames, delay_ms


def first_frame(path: Path) -> Image.Image:
    """Return the first frame of a video as an RGB image."""
    cap = cv2.VideoCapture(str(path))
    try:
        ok, bgr = cap.read()
    finally:
        cap.release()
    if not ok:
        raise ValueError(f"No se pudo leer el video: {Path(path).name}")
    return Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))

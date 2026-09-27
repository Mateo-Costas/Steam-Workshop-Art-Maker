"""gif_utils - GIF helpers that also work on Steam-patched files.

Finished fragments get their last byte changed from the GIF trailer (0x3B)
to 0x21 so Steam renders them at full width (see _patch_gif_trailer). Pillow
cannot open such files (IndexError while looking for the next block), so any
code that reads a fragment back must go through these helpers:

    open_gif(path)      -> PIL image, trailer restored in memory
    read_timing(path)   -> size and per-frame delays, parsed without decoding
    playback_fps(path)  -> frame rate to resample at without changing speed
"""
import io
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from PIL import Image

GIF_TRAILER = 0x3B
STEAM_TRAILER = 0x21

#: Browsers (and Steam) play delays below 20 ms at 100 ms, so 50 fps is the
#: fastest rate a GIF can really have. ffmpeg's GIF demuxer applies the same rule.
MIN_DELAY_MS = 20
MAX_GIF_FPS = 1000 / MIN_DELAY_MS
DEFAULT_DELAY_MS = 100


def read_gif_bytes(path: Path) -> bytes:
    """Return the file bytes with a Steam-patched trailer restored to 0x3B."""
    data = Path(path).read_bytes()
    if data[:3] == b"GIF" and data and data[-1] == STEAM_TRAILER:
        data = data[:-1] + bytes([GIF_TRAILER])
    return data


def open_gif(path: Path) -> Image.Image:
    """Open a GIF (patched or not) with Pillow. The caller closes the image."""
    return Image.open(io.BytesIO(read_gif_bytes(path)))


def open_image(path: Path) -> Image.Image:
    """Open any image; GIFs go through open_gif so patched files work."""
    if Path(path).suffix.lower() == ".gif":
        return open_gif(path)
    return Image.open(path)


@dataclass
class GifTiming:
    """Canvas size and per-frame delays (ms) of a GIF."""
    width: int = 0
    height: int = 0
    delays: List[int] = field(default_factory=list)

    @property
    def frames(self) -> int:
        return len(self.delays)

    @property
    def effective_delays(self) -> List[int]:
        """Delays as players show them (sub-20 ms delays play at 100 ms)."""
        return [d if d >= MIN_DELAY_MS else DEFAULT_DELAY_MS for d in self.delays]

    @property
    def duration_ms(self) -> int:
        return sum(self.effective_delays)


def read_timing(path: Path) -> GifTiming:
    """Parse the block structure of a GIF without decoding any pixel data.

    Tolerates the Steam-patched trailer. Raises ValueError for non-GIF files.
    """
    data = Path(path).read_bytes()
    if data[:6] not in (b"GIF87a", b"GIF89a"):
        raise ValueError(f"No es un GIF: {path}")
    width, height, flags = struct.unpack("<HHB", data[6:11])
    pos = 13
    if flags & 0x80:
        pos += 3 * (2 << (flags & 0x07))
    timing = GifTiming(width, height)
    pending_delay = 0
    size = len(data)
    while pos < size:
        block = data[pos]
        if block == GIF_TRAILER:
            break
        if block == STEAM_TRAILER:  # extension (or the patched trailer at EOF)
            if pos + 1 >= size:
                break
            label = data[pos + 1]
            pos += 2
            first = True
            while pos < size:
                length = data[pos]
                pos += 1
                if length == 0:
                    break
                if first and label == 0xF9 and length >= 4:
                    pending_delay = struct.unpack("<H", data[pos + 1:pos + 3])[0] * 10
                first = False
                pos += length
        elif block == 0x2C:  # image descriptor
            local_flags = data[pos + 9]
            pos += 10
            if local_flags & 0x80:
                pos += 3 * (2 << (local_flags & 0x07))
            pos += 1  # LZW minimum code size
            while pos < size:
                length = data[pos]
                pos += 1
                if length == 0:
                    break
                pos += length
            timing.delays.append(pending_delay)
            pending_delay = 0
        else:
            break  # unknown block: stop, keep what was parsed
    return timing


def playback_fps(path: Path) -> float:
    """Frame rate to resample a GIF at without changing its speed or motion.

    GIF delays are whole centiseconds, so a 24 fps clip is stored as a mix of
    40 and 50 ms: for near-uniform delays the true rate is frames/duration.
    When delays vary a lot (gifski merges identical frames into long delays,
    hand-made GIFs hold some frames) the shortest delay is the real frame
    period. Capped at the 50 fps GIF maximum.
    """
    try:
        delays = read_timing(path).effective_delays
    except (OSError, ValueError):
        delays = []
    if not delays:
        return 1000.0 / DEFAULT_DELAY_MS
    shortest = min(delays)
    if max(delays) <= shortest * 1.5:
        fps = len(delays) * 1000.0 / sum(delays)
    else:
        fps = 1000.0 / shortest
    return round(min(MAX_GIF_FPS, fps), 3)


def format_fps(fps: float) -> str:
    """Render an fps value for command lines ("25", "33.333")."""
    return f"{fps:.3f}".rstrip("0").rstrip(".")

"""processing.common - shared constants, logger and the subprocess helper."""
import logging
import subprocess
import sys
from typing import List

# Hide the console window Windows opens for every subprocess.
_NO_WINDOW_FLAGS = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}

logger = logging.getLogger("WorkshopArt.processor")

#: Steam rejects artwork/workshop uploads above 5 MiB (5,242,880 bytes).
STEAM_MAX_BYTES = 5 * 1024 * 1024
#: Fragments are encoded with 16 KiB of headroom below the hard limit.
FRAGMENT_MAX_BYTES = STEAM_MAX_BYTES - 16 * 1024


def run_tool(cmd: List[str], timeout: float) -> subprocess.CompletedProcess:
    """Run an external tool (ffmpeg, gifski, gifsicle...) and capture its output.

    Never raises for a non-zero exit code; callers check ``returncode``.
    Timeouts and a missing executable are reported as returncode -1.
    """
    try:
        return subprocess.run([str(part) for part in cmd], capture_output=True,
                              encoding="utf-8", errors="replace",
                              timeout=timeout, **_NO_WINDOW_FLAGS)
    except subprocess.TimeoutExpired:
        logger.error("Timeout (%ss) ejecutando %s", int(timeout), cmd[0])
        return subprocess.CompletedProcess(cmd, -1, "", f"timeout tras {int(timeout)} s")
    except OSError as e:
        logger.error("No se pudo ejecutar %s: %s", cmd[0], e)
        return subprocess.CompletedProcess(cmd, -1, "", str(e))


def tail(text: str, chars: int = 300) -> str:
    """Last ``chars`` characters of a tool's stderr, for error messages."""
    return (text or "").strip()[-chars:]

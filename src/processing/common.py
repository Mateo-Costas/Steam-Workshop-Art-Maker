"""processing.common - shared constants, logger and the subprocess helper."""
import logging
import subprocess
import sys
import time
from typing import Callable, List, Optional

# Hide the console window Windows opens for every subprocess.
_NO_WINDOW_FLAGS = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}

logger = logging.getLogger("WorkshopArt.processor")

#: Steam rejects artwork/workshop uploads above 5 MiB (5,242,880 bytes).
STEAM_MAX_BYTES = 5 * 1024 * 1024
#: Fragments are encoded with 16 KiB of headroom below the hard limit.
FRAGMENT_MAX_BYTES = STEAM_MAX_BYTES - 16 * 1024

#: ``should_cancel()`` callbacks: return True to stop the running job.
CancelFn = Optional[Callable[[], bool]]

#: How often a running tool checks whether the user pressed Cancel (seconds).
_CANCEL_POLL_S = 0.25


def run_tool(cmd: List[str], timeout: float,
             should_cancel: CancelFn = None) -> subprocess.CompletedProcess:
    """Run an external tool (ffmpeg, gifski, gifsicle...) and capture its output.

    Never raises for a non-zero exit code; callers check ``returncode``.
    Timeouts and a missing executable are reported as returncode -1. While
    the tool runs ``should_cancel`` is polled: when it returns True the
    process is killed and InterruptedError is raised, so Cancel stops even a
    long FFmpeg encode right away.
    """
    args = [str(part) for part in cmd]
    try:
        process = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, encoding="utf-8", errors="replace",
                                   **_NO_WINDOW_FLAGS)
    except OSError as e:
        logger.error("No se pudo ejecutar %s: %s", args[0], e)
        return subprocess.CompletedProcess(args, -1, "", str(e))

    deadline = time.monotonic() + timeout
    while True:
        remaining = max(0.01, deadline - time.monotonic())
        wait = min(_CANCEL_POLL_S, remaining) if should_cancel else remaining
        try:
            stdout, stderr = process.communicate(timeout=wait)
            return subprocess.CompletedProcess(args, process.returncode, stdout, stderr)
        except subprocess.TimeoutExpired:
            if should_cancel and should_cancel():
                _kill(process)
                raise InterruptedError("Cancelado por el usuario")
            if time.monotonic() >= deadline:
                _kill(process)
                logger.error("Timeout (%ss) ejecutando %s", int(timeout), args[0])
                return subprocess.CompletedProcess(args, -1, "", f"timeout tras {int(timeout)} s")


def _kill(process: subprocess.Popen) -> None:
    """Terminate a tool and reap it (its pipes are drained so it cannot hang)."""
    try:
        process.kill()
        process.communicate(timeout=10)
    except (OSError, subprocess.SubprocessError):
        pass


def check_cancel(should_cancel: CancelFn) -> None:
    """Raise InterruptedError when the user asked to cancel."""
    if should_cancel and should_cancel():
        raise InterruptedError("Cancelado por el usuario")


def tail(text: str, chars: int = 300) -> str:
    """Last ``chars`` characters of a tool's stderr, for error messages."""
    return (text or "").strip()[-chars:]

"""ui.logic.common - shared constants and helpers for the logic mixins."""
import platform
import subprocess
from typing import Optional

from analyzers import ContentAnalyzer as _ContentAnalyzer

# Suppress the console window that Windows spawns for subprocess calls.
_NO_WINDOW_FLAGS = {'creationflags': subprocess.CREATE_NO_WINDOW} if platform.system() == 'Windows' else {}

# Used throughout to distinguish static images from animated formats.
_STATIC_IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.bmp', '.webp'}


def _steam_format_suggestion(w: int, h: int) -> Optional[str]:
    """Delegates to ContentAnalyzer._get_upload_suggestion - single source of truth."""
    if h <= 0:
        return None
    return _ContentAnalyzer._get_upload_suggestion(w, h)

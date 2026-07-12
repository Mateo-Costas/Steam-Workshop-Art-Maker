"""processing.common - shared constants and logger for the processing package."""
import logging
import platform
import subprocess

# Hide subprocess console windows on Windows
_NO_WINDOW_FLAGS = {'creationflags': subprocess.CREATE_NO_WINDOW} if platform.system() == 'Windows' else {}

logger = logging.getLogger("WorkshopArtPRO.processor")

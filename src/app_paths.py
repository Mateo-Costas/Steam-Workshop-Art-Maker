"""app_paths - absolute locations of WorkshopArt's files and bundled tools.

Everything is resolved from the application folder (the .exe folder when
frozen with PyInstaller, the repository root when running from source), never
from the current working directory, so the app behaves the same no matter
where it is launched from.
"""
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Optional

APP_VERSION = "2.1"

FROZEN = getattr(sys, "frozen", False)

#: Folder that holds config.json and SteamWorkshopAppData/.
APP_DIR = (Path(sys.executable).parent if FROZEN
           else Path(__file__).resolve().parent.parent)
DATA_DIR = APP_DIR / "SteamWorkshopAppData"
TEMP_DIR = DATA_DIR / "temp"
LOGS_DIR = DATA_DIR / "logs"
MODELS_DIR = DATA_DIR / "models"
RIFE_DIR = DATA_DIR / "rife"
CONFIG_FILE = APP_DIR / "config.json"

_EXE_SUFFIX = ".exe" if sys.platform == "win32" else ""


def resolve(path_value) -> Path:
    """Return ``path_value`` as an absolute path, relative ones anchored at APP_DIR."""
    path = Path(path_value)
    return path if path.is_absolute() else APP_DIR / path


def find_tool(name: str) -> Optional[Path]:
    """Locate a bundled or system-installed executable (``name`` without .exe).

    Search order: SteamWorkshopAppData/ (where the app downloads tools), the
    app folder (legacy layout), PyInstaller's _internal/ and finally PATH.
    """
    filename = name + _EXE_SUFFIX
    for folder in (DATA_DIR, APP_DIR, APP_DIR / "_internal"):
        candidate = folder / filename
        if candidate.exists():
            return candidate
    system = shutil.which(name)
    return Path(system) if system else None


def make_temp_dir(prefix: str) -> Path:
    """Create a unique working folder inside SteamWorkshopAppData/temp.

    The temp folder is emptied when the app closes, so it is (re)created here.
    """
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix=prefix, dir=TEMP_DIR))


def ensure_dirs() -> None:
    """Create the runtime folder tree (idempotent)."""
    for folder in (DATA_DIR, TEMP_DIR, LOGS_DIR, MODELS_DIR, RIFE_DIR):
        folder.mkdir(parents=True, exist_ok=True)

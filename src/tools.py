"""tools - download and install the external programs WorkshopArt runs.

FFmpeg (required) and gifski (best GIF encoder) are installed on first launch,
RIFE (frame interpolation, ~410 MB) the first time it is used. Archives come
from the official releases and are verified before anything is extracted
(see downloads.py); only the files the app needs are written, by name, into
SteamWorkshopAppData/.
"""
import re
import tarfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Callable, Optional, Tuple

import requests

from app_paths import APP_DIR, DATA_DIR, RIFE_DIR, find_tool
from downloads import IntegrityError, download_file, published_sha256

Log = Callable[[str, Optional[float]], None]
CancelFn = Optional[Callable[[], bool]]

FFMPEG_URL = ("https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/"
              "ffmpeg-master-latest-win64-gpl.zip")
#: BtbN rebuilds "latest" every day and publishes the SHA-256 of each asset here.
FFMPEG_SUMS_URL = ("https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/"
                   "checksums.sha256")

GIFSKI_API = "https://api.github.com/repos/ImageOptim/gifski/releases/latest"
GIFSKI_FALLBACK_URL = ("https://github.com/ImageOptim/gifski/releases/download/1.34.0/"
                       "gifski-1.34.0.tar.xz")
GIFSKI_FALLBACK_SHA256 = "b9b6591aa163123d737353d9c8581efdf3234d28eeaa45329b31da905cd5a996"

RIFE_URL = ("https://github.com/nihui/rife-ncnn-vulkan/releases/download/20221029/"
            "rife-ncnn-vulkan-20221029-windows.zip")
RIFE_SHA256 = "d8e4d772d26cd8006ef0ad0bc82eb191b53c68677d1ae2f42506d74cbbbea606"
#: Size of the RIFE release (431,540,241 bytes), shown before downloading it.
RIFE_DOWNLOAD_MB = 412
#: RIFE model folders, best first. Only these are extracted from the release.
RIFE_MODELS = ("rife-v4.6", "rife-v4", "rife-v3.1", "rife-v3.0", "rife-HD")

#: Names an extracted tool file may have: no folders, drive letters or streams.
_SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._ -]*$")


def safe_member_name(member_name: str) -> Optional[str]:
    """File name of an archive member, or None if it is unsafe to write.

    Archive paths are untrusted: only the last component is kept and it must
    be a plain file name ("..", "C:x.exe" or "x.exe:stream" are rejected).
    """
    normalized = member_name.replace("\\", "/")
    if normalized.endswith("/"):
        return None  # a folder entry
    name = PurePosixPath(normalized).name
    if not name or name in (".", "..") or not _SAFE_NAME_RE.match(name):
        return None
    return name


def member_parts(member_name: str) -> Tuple[str, ...]:
    """Path components of an archive member, with either kind of separator."""
    return PurePosixPath(member_name.replace("\\", "/")).parts


def extract_member(archive: Path, wanted: str, dest: Path) -> bool:
    """Copy the first archive member whose file name is ``wanted`` to ``dest``."""
    if archive.name.endswith((".tar.xz", ".tar.gz", ".tgz")):
        with tarfile.open(archive) as tf:
            for member in tf.getmembers():
                if member.isfile() and (safe_member_name(member.name) or "").lower() == wanted:
                    dest.write_bytes(tf.extractfile(member).read())
                    return True
        return False
    with zipfile.ZipFile(archive) as zf:
        for name in zf.namelist():
            if (safe_member_name(name) or "").lower() == wanted:
                dest.write_bytes(zf.read(name))
                return True
    return False


# ---------------------------------------------------------------------------
# Installers (run in worker threads; ``log(message, percent)`` reports progress)
# ---------------------------------------------------------------------------
def install_ffmpeg(work: Path, log: Log) -> None:
    """Latest FFmpeg build, checked against the checksum list of the same release."""
    filename = Path(FFMPEG_URL).name
    for attempt in (1, 2):
        expected = published_sha256(FFMPEG_SUMS_URL, filename)
        if expected is None:
            log("Aviso: no se pudo obtener el checksum de FFmpeg; se descarga sin verificar", None)
        try:
            archive = download_file(FFMPEG_URL, work / "ffmpeg.zip", "FFmpeg", log, sha256=expected)
            break
        except IntegrityError:
            # "latest" may have been rebuilt between the two requests.
            if attempt == 2:
                raise
            log("El checksum de FFmpeg no coincide; reintentando la descarga...", None)
    if not extract_member(archive, "ffmpeg.exe", DATA_DIR / "ffmpeg.exe"):
        raise RuntimeError("ffmpeg.exe no esta en el archivo descargado")


def install_gifski(work: Path, log: Log) -> None:
    """gifski's latest release (a .tar.xz with binaries for every OS: win/gifski.exe)."""
    url, expected = GIFSKI_FALLBACK_URL, GIFSKI_FALLBACK_SHA256
    try:
        release = requests.get(GIFSKI_API, timeout=15,
                               headers={"Accept": "application/vnd.github+json",
                                        "User-Agent": "WorkshopArt"}).json()
        for asset in release.get("assets", []):
            name = str(asset.get("name", ""))
            link = str(asset.get("browser_download_url", ""))
            if (name.endswith((".tar.xz", ".zip")) and "deb" not in name
                    and link.startswith("https://github.com/ImageOptim/gifski/releases/download/")):
                # GitHub publishes "sha256:<hex>" digests for release assets.
                url, expected = link, asset.get("digest")
                break
    except (requests.RequestException, ValueError, AttributeError) as e:
        log(f"GitHub API no disponible ({e}), usando gifski 1.34.0", None)
    if not expected:
        log("Aviso: GitHub no publica el checksum de este gifski; se descarga sin verificar", None)
    archive = download_file(url, work / (safe_member_name(url) or "gifski.tar.xz"), "gifski",
                            log, sha256=expected)
    if not extract_member(archive, "gifski.exe", DATA_DIR / "gifski.exe"):
        raise RuntimeError("gifski.exe no esta en el archivo descargado")


def install_rife(work: Path, log: Log, should_cancel: CancelFn = None) -> None:
    """rife-ncnn-vulkan (pinned release): the exe, its runtime DLL and the RIFE_MODELS folders."""
    archive = download_file(RIFE_URL, work / "rife.zip", "RIFE", log, sha256=RIFE_SHA256,
                            should_cancel=should_cancel)
    log("Extrayendo RIFE...", None)
    with zipfile.ZipFile(archive) as zf:
        for member in zf.infolist():
            parts = member_parts(member.filename)
            name = safe_member_name(member.filename)
            if member.is_dir() or len(parts) < 2 or not name:
                continue
            if name.lower().endswith((".exe", ".dll")) and "vcomp140d" not in name.lower():
                dest = DATA_DIR / name
            elif parts[-2] in RIFE_MODELS and name.endswith((".bin", ".param")):
                dest = RIFE_DIR / parts[-2] / name
            else:
                continue  # sample images, readme and the models the app never uses
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(zf.read(member))


def find_rife_model() -> Tuple[Optional[str], Optional[Path]]:
    """(name, folder) of the best installed RIFE model, or (None, None)."""
    for name in RIFE_MODELS:
        for base in (RIFE_DIR, APP_DIR):
            folder = base / name
            if any(folder.glob("*.bin")) and any(folder.glob("*.param")):
                return name, folder
    return None, None


def rife_installed() -> bool:
    """True when the RIFE executable and at least one of its models are present."""
    return find_tool("rife-ncnn-vulkan") is not None and find_rife_model()[0] is not None

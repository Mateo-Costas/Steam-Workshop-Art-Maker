"""downloads - verified streaming downloads for the bundled tools and models.

The app downloads executables (FFmpeg, gifski, gifsicle, Real-ESRGAN,
Real-CUGAN, RIFE) and then runs them, so every archive is checked before it
is used: pinned releases against the SHA-256 recorded here when the release
was added, rolling builds against the checksum their publisher lists next to
them. A mismatch deletes the file and raises IntegrityError.
"""
import hashlib
import logging
import re
from pathlib import Path
from typing import Callable, Optional

import requests

logger = logging.getLogger("WorkshopArt.downloads")

ProgressFn = Optional[Callable[[str, float], None]]

_USER_AGENT = "WorkshopArt"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class IntegrityError(OSError):
    """A downloaded file is incomplete or does not match its expected SHA-256."""


def download_file(url: str, dest: Path, label: str, progress: ProgressFn = None,
                  timeout: float = 90, sha256: Optional[str] = None,
                  should_cancel: Optional[Callable[[], bool]] = None) -> Path:
    """Download ``url`` to ``dest`` (written as .part first, renamed when complete).

    ``progress(message, percent)`` is called at most every 5%. When ``sha256``
    is given the content must match it. Raises requests.RequestException,
    OSError or IntegrityError (an OSError) on failure, and InterruptedError
    when ``should_cancel()`` becomes true; nothing is left at ``dest`` unless
    the download is complete and verified.
    """
    expected = _normalize_sha256(sha256) if sha256 else None
    dest.parent.mkdir(parents=True, exist_ok=True)
    partial = dest.with_name(dest.name + ".part")
    digest = hashlib.sha256()
    try:
        with requests.get(url, stream=True, timeout=timeout,
                          headers={"User-Agent": _USER_AGENT}) as response:
            response.raise_for_status()
            total = int(response.headers.get("content-length", 0) or 0)
            # A compressed transfer reports the compressed length: only an
            # uncompressed one can be compared byte for byte.
            if response.headers.get("content-encoding", "identity").lower() not in ("", "identity"):
                total = 0
            done, last_step = 0, -1
            with open(partial, "wb") as f:
                for chunk in response.iter_content(chunk_size=256 * 1024):
                    if should_cancel and should_cancel():
                        raise InterruptedError("Descarga cancelada")
                    f.write(chunk)
                    digest.update(chunk)
                    done += len(chunk)
                    if progress and total:
                        step = int(done * 20 / total)  # 5 % steps
                        if step != last_step:
                            last_step = step
                            progress(f"{label}: {done / 1048576:.0f}/{total / 1048576:.0f} MB",
                                     done * 100.0 / total)
        if total and done != total:
            raise IntegrityError(f"{label}: descarga incompleta ({done} de {total} bytes)")
        if expected and digest.hexdigest() != expected:
            raise IntegrityError(f"{label}: el SHA-256 no coincide (archivo dañado o alterado)")
        partial.replace(dest)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
    logger.info("Descargado %s (%.1f MB%s)", dest.name, dest.stat().st_size / 1048576,
                ", SHA-256 verificado" if expected else "")
    return dest


def published_sha256(checksums_url: str, filename: str, timeout: float = 30) -> Optional[str]:
    """SHA-256 of ``filename`` from a ``sha256sum``-style list ("<hex>  <name>" lines).

    Returns None when the list cannot be fetched or does not mention the file,
    so callers decide whether to continue unverified.
    """
    try:
        response = requests.get(checksums_url, timeout=timeout,
                                headers={"User-Agent": _USER_AGENT})
        response.raise_for_status()
        text = response.text
    except requests.RequestException as e:
        logger.warning("No se pudo leer la lista de checksums %s: %s", checksums_url, e)
        return None
    return parse_sha256_list(text, filename)


def parse_sha256_list(text: str, filename: str) -> Optional[str]:
    """Find ``filename`` in a ``sha256sum`` output (binary-mode "*name" accepted)."""
    for line in text.splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) == 2 and parts[1].lstrip("*").strip() == filename:
            try:
                return _normalize_sha256(parts[0])
            except ValueError:
                return None
    return None


def _normalize_sha256(value: str) -> str:
    """Lower-case hex digest; accepts the "sha256:<hex>" form GitHub uses."""
    value = value.strip().lower()
    if value.startswith("sha256:"):
        value = value[len("sha256:"):]
    if not _SHA256_RE.match(value):
        raise ValueError(f"SHA-256 no válido: {value!r}")
    return value

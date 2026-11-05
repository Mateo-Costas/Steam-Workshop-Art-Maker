"""updates - tell the user when a newer WorkshopArt release is published.

One anonymous request to the GitHub Releases API a few seconds after the
window opens (at most once a day, see the "updates" section of config.json,
which also turns the check off). Nothing is downloaded or installed: the
header shows a button that opens the release page.
"""
import logging
import re
import time
from typing import Optional, Tuple

import requests

logger = logging.getLogger("WorkshopArt.updates")

REPO = "Mateo-Costas/Steam-Workshop-Art-Maker"
RELEASES_API = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases/latest"

#: Seconds between two checks.
CHECK_INTERVAL_S = 24 * 3600

_VERSION_RE = re.compile(r"(\d+(?:\.\d+)*)")


def parse_version(text: str) -> Tuple[int, ...]:
    """(2, 10) from "v2.10", "WorkshopArt 2.10" or "2.10.0" (trailing zeros dropped)."""
    match = _VERSION_RE.search(text or "")
    if not match:
        return ()
    parts = [int(p) for p in match.group(1).split(".")]
    while len(parts) > 1 and parts[-1] == 0:
        parts.pop()
    return tuple(parts)


def is_newer(candidate: str, current: str) -> bool:
    """True when version ``candidate`` is strictly newer than ``current``."""
    new, old = parse_version(candidate), parse_version(current)
    return bool(new) and new > old


def latest_release(timeout: float = 8) -> Optional[dict]:
    """{"version", "url"} of the latest published release, or None (offline, rate limit...)."""
    try:
        response = requests.get(RELEASES_API, timeout=timeout,
                                headers={"Accept": "application/vnd.github+json",
                                         "User-Agent": "WorkshopArt"})
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError) as e:
        logger.info("No se pudo comprobar si hay actualizaciones: %s", e)
        return None
    if not isinstance(data, dict) or data.get("draft") or data.get("prerelease"):
        return None
    tag = str(data.get("tag_name") or "")
    url = str(data.get("html_url") or "")
    if not url.startswith(f"https://github.com/{REPO}/"):
        url = RELEASES_PAGE
    return {"version": tag.lstrip("vV"), "url": url} if parse_version(tag) else None


def check_for_update(config, current_version: str, force: bool = False) -> Optional[dict]:
    """The newer release to announce, or None.

    Honours config "updates.check" (off = never) and checks at most once per
    CHECK_INTERVAL_S unless ``force``; the last answer is cached in config so
    the button keeps showing between checks.
    """
    if not config.get("updates.check", True):
        return None
    now = time.time()
    last = float(config.get("updates.last_check", 0) or 0)
    if force or now - last >= CHECK_INTERVAL_S:
        release = latest_release()
        if release is not None:
            config.set("updates.latest", release)
        config.set("updates.last_check", now)
    cached = config.get("updates.latest") or {}
    version = str(cached.get("version", "")) if isinstance(cached, dict) else ""
    if version and is_newer(version, current_version):
        url = str(cached.get("url") or RELEASES_PAGE)
        return {"version": version,
                "url": url if url.startswith(f"https://github.com/{REPO}/") else RELEASES_PAGE}
    return None

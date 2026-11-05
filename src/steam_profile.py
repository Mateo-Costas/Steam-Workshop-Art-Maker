"""steam_profile - public Steam profile lookups (Community XML endpoint, no API key).

Whatever the user types (a custom URL name, a SteamID64 or a profile link) is
normalised by profile_url() into an https://steamcommunity.com/... address:
the app never fetches a URL on another host. Responses are size-capped and
the avatar is only downloaded from Steam's image CDN and decoded as a
JPEG/PNG/GIF/WEBP picture.
"""
import io
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from typing import Callable, Optional

from PIL import Image

from i18n import t

PROFILE_HOST = "steamcommunity.com"
#: Hosts Steam serves avatars from (subdomains included).
_AVATAR_HOSTS = ("steamstatic.com", "akamaihd.net", "steamcommunity.com")
_AVATAR_FORMATS = ("JPEG", "PNG", "GIF", "WEBP")

_MAX_XML_BYTES = 1 * 1024 * 1024
_MAX_HTML_BYTES = 4 * 1024 * 1024
_MAX_AVATAR_BYTES = 2 * 1024 * 1024

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}
_STEAMID64_RE = re.compile(r"^7656\d{13}$")
_VANITY_RE = re.compile(r"^[A-Za-z0-9_-]{2,64}$")
_LEVEL_RE = re.compile(r'friendPlayerLevelNum">\s*(\d+)')


def profile_url(raw: str) -> str:
    """Canonical https://steamcommunity.com/id/<name> or /profiles/<id64> URL.

    Accepts a custom URL name, a 17-digit SteamID64 or a profile link (with
    or without scheme, http or https). Raises ValueError for anything else,
    including links to other sites.
    """
    text = (raw or "").strip()
    if _STEAMID64_RE.match(text):
        return f"https://{PROFILE_HOST}/profiles/{text}"
    if _VANITY_RE.match(text):
        return f"https://{PROFILE_HOST}/id/{text}"
    link = text if "://" in text else "https://" + text
    parsed = urllib.parse.urlsplit(link)
    host = (parsed.hostname or "").lower()
    parts = [p for p in parsed.path.split("/") if p]
    if (parsed.scheme in ("http", "https") and host in (PROFILE_HOST, "www." + PROFILE_HOST)
            and len(parts) >= 2):
        kind, value = parts[0].lower(), urllib.parse.unquote(parts[1])
        if kind == "profiles" and _STEAMID64_RE.match(value):
            return f"https://{PROFILE_HOST}/profiles/{value}"
        if kind == "id" and _VANITY_RE.match(value):
            return f"https://{PROFILE_HOST}/id/{value}"
    raise ValueError(t("profile_bad_url",
                       fallback="Escribe tu nombre personalizado, tu SteamID64 o el enlace "
                                "a tu perfil de steamcommunity.com"))


def _read(url: str, limit: int, timeout: float) -> bytes:
    """GET ``url`` and return at most ``limit`` bytes (larger answers are refused)."""
    request = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(request, timeout=timeout) as response:  # nosec: fixed hosts
        data = response.read(limit + 1)
    if len(data) > limit:
        raise OSError(f"respuesta demasiado grande de {urllib.parse.urlsplit(url).hostname}")
    return data


def _is_avatar_url(url: str) -> bool:
    parsed = urllib.parse.urlsplit(url)
    host = (parsed.hostname or "").lower()
    return parsed.scheme == "https" and any(host == h or host.endswith("." + h)
                                            for h in _AVATAR_HOSTS)


class ProfileFetcher:
    """Public profile data (name, avatar, online state) of a Steam profile."""

    def fetch(self, raw_profile: str, status_cb: Callable[[str], None] = lambda _m: None) -> dict:
        """Return {'name': str, 'avatar': PIL image or None, 'online': bool, 'url': str}.

        ``raw_profile`` is anything profile_url() accepts. Raises ValueError
        for an invalid profile and RuntimeError when Steam cannot be reached
        or the profile is private / missing.
        """
        url = profile_url(raw_profile)
        status_cb(t("profile_checking", fallback="Consultando Steam..."))
        try:
            raw = _read(url + "/?xml=1", _MAX_XML_BYTES, timeout=12)
        except OSError as exc:
            raise RuntimeError(t("steam_unreachable", fallback="No se pudo conectar con Steam: {err}",
                                 err=exc)) from exc
        try:
            root = ET.fromstring(raw)
        except ET.ParseError as exc:
            raise RuntimeError(t("steam_bad_answer",
                                 fallback="Respuesta inesperada de Steam (¿perfil privado?)")) from exc
        error = root.findtext("error")
        if error:
            raise RuntimeError(t("profile_unavailable", fallback="Perfil no disponible: {err}", err=error))

        name = root.findtext("steamID") or "SteamUser"
        avatar_url = (root.findtext("avatarFull") or root.findtext("avatarMedium") or "").strip()
        online = (root.findtext("onlineState") or "").lower() in ("online", "in-game")
        avatar = None
        if avatar_url and _is_avatar_url(avatar_url):
            try:
                data = _read(avatar_url, _MAX_AVATAR_BYTES, timeout=10)
                with Image.open(io.BytesIO(data), formats=_AVATAR_FORMATS) as image:
                    avatar = image.convert("RGB")
            except OSError:
                pass  # the avatar is optional
        return {"name": name, "avatar": avatar, "online": online, "url": url}

    @staticmethod
    def fetch_level(url: str) -> Optional[int]:
        """Steam level shown on a profile page (None when it can't be read)."""
        try:
            html = _read(profile_url(url), _MAX_HTML_BYTES, timeout=12).decode("utf-8", "replace")
        except (OSError, ValueError):
            return None
        match = _LEVEL_RE.search(html)
        return int(match.group(1)) if match else None

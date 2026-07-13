"""
steam_uploader.py - Auto-upload de fragmentos a Steam Workshop (uso personal).

PRIVADO: este archivo está gitignoreado.

Carga de credenciales (en orden de preferencia):
  1. browser_cookie3 leyendo Firefox automáticamente (recomendado).
  2. Fallback: `steam_cookies.json` en la raíz del proyecto con las claves
     {"sessionid": "...", "steamLoginSecure": "..."}.

Pre-requisito browser_cookie3:  pip install browser_cookie3
Cierra Firefox antes si Windows bloquea cookies.sqlite.
"""
from __future__ import annotations
import json
import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Fijar PLAYWRIGHT_BROWSERS_PATH a una ruta permanente ANTES de que playwright
# se importe o inicialice. En frozen mode el temp dir (_MEI*) se destruye al
# cerrar la app, por lo que los browsers instalados ahi se pierden.
# ---------------------------------------------------------------------------
_PW_BROWSERS_DIR = (
    Path(sys.executable).parent / "SteamWorkshopAppData" / "browsers"
    if getattr(sys, 'frozen', False)
    else Path(__file__).parent.parent / "SteamWorkshopAppData" / "browsers"
)
_PW_BROWSERS_DIR.mkdir(parents=True, exist_ok=True)
os.environ['PLAYWRIGHT_BROWSERS_PATH'] = str(_PW_BROWSERS_DIR)

import requests

# Rutas: junto al exe en builds frozen, junto al script en desarrollo
_BASE_DIR = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).parent.parent
COOKIES_FILE = _BASE_DIR / "steam_cookies.json"
LOGS_DIR = _BASE_DIR / "SteamWorkshopAppData" / "logs"
LOGS_KEEP_N = 10          # rotar dumps, mantener últimos N pares
UPLOAD_URL = "https://steamcommunity.com/sharedfiles/edititem/767/3/"
SUBMIT_URL = "https://steamcommunity.com/sharedfiles/submititem/"
WORKSHOP_APP_ID = "767"   # 767 = Steam genérico (no asociado a juego concreto)
CONSUMER_APP_ID = "767"   # también 767 — artwork no-de-un-juego
FILE_TYPE = "3"           # file_type por defecto: artwork (3). Workshop=0, Screenshot=5
VISIBILITY = "0"          # Public
UPLOAD_DELAY_SEC = 15     # espera entre uploads para evitar LimitExceeded


# ---------------------------------------------------------------------------
# Carga de cookies
# ---------------------------------------------------------------------------

_COOKIES_CACHE: Optional[Tuple[str, requests.cookies.RequestsCookieJar]] = None


_SENSITIVE_COOKIE_RE = re.compile(
    r'("(?:steamLoginSecure|sessionid|wg_hmac|steamMachineAuth\w*|steamRefresh_steam)"\s*:\s*")[^"]*(")'
    r'|((?:steamLoginSecure|sessionid|wg_hmac|steamMachineAuth\w*|steamRefresh_steam)=)[^;"&\s]+',
    re.IGNORECASE,
)


def _redact_sensitive(text: str) -> str:
    """Reemplazar valores de cookies/tokens de sesion antes de volcar HTML a disco,
    para que los logs de fallo compartidos por soporte no filtren credenciales."""
    def _sub(m: "re.Match") -> str:
        if m.group(1) is not None:
            return f"{m.group(1)}[REDACTED]{m.group(2)}"
        return f"{m.group(3)}[REDACTED]"
    try:
        return _SENSITIVE_COOKIE_RE.sub(_sub, text)
    except Exception:
        return text


def _rotate_logs() -> None:
    """Mantener solo los últimos N dumps de cada tipo."""
    try:
        if not LOGS_DIR.exists():
            return
        for pattern in ("upload_fail_*.html", "uploadartwork_get_*.html",
                        "up_*.gif", "up_*.jpg", "up_*.png"):
            files = sorted(LOGS_DIR.glob(pattern), key=lambda p: p.stat().st_mtime)
            for old in files[:-LOGS_KEEP_N]:
                try:
                    old.unlink()
                except OSError:
                    pass
    except Exception:
        pass


def _load_cookies_from_firefox() -> Optional[requests.cookies.RequestsCookieJar]:
    """Leer cookies de Firefox directamente (browser_cookie3)."""
    try:
        import browser_cookie3
    except ImportError:
        return None
    try:
        # Leer de TODOS los dominios Steam (sessionid puede estar en otro subdominio)
        cj = browser_cookie3.firefox()
        relevant = [c for c in cj if "steam" in (c.domain or "").lower()]
        names = {c.name for c in relevant}
        # steamLoginSecure es el único crítico. sessionid se puede bootstrapear.
        if "steamLoginSecure" not in names:
            return None
        jar = requests.cookies.RequestsCookieJar()
        for c in relevant:
            jar.set(c.name, c.value, domain=c.domain or ".steamcommunity.com", path=c.path or "/")
        return jar
    except Exception as e:
        logger.debug(f"No se pudieron leer cookies de Firefox: {e}")
        return None


def _load_cookies_from_chrome() -> Optional[requests.cookies.RequestsCookieJar]:
    try:
        import browser_cookie3
    except ImportError:
        return None
    try:
        cj = browser_cookie3.chrome()
        relevant = [c for c in cj if "steam" in (c.domain or "").lower()]
        if "steamLoginSecure" not in {c.name for c in relevant}:
            return None
        jar = requests.cookies.RequestsCookieJar()
        for c in relevant:
            jar.set(c.name, c.value, domain=c.domain or ".steamcommunity.com", path=c.path or "/")
        return jar
    except Exception as e:
        logger.debug(f"No se pudieron leer cookies de Chrome: {e}")
        return None


def _load_cookies_from_edge() -> Optional[requests.cookies.RequestsCookieJar]:
    try:
        import browser_cookie3
    except ImportError:
        return None
    try:
        cj = browser_cookie3.edge()
        relevant = [c for c in cj if "steam" in (c.domain or "").lower()]
        if "steamLoginSecure" not in {c.name for c in relevant}:
            return None
        jar = requests.cookies.RequestsCookieJar()
        for c in relevant:
            jar.set(c.name, c.value, domain=c.domain or ".steamcommunity.com", path=c.path or "/")
        return jar
    except Exception as e:
        logger.debug(f"No se pudieron leer cookies de Edge: {e}")
        return None


def _restrict_cookie_file_permissions() -> None:
    """Best-effort: dejar steam_cookies.json legible/escribible solo por el owner."""
    try:
        if sys.platform == "win32":
            import subprocess
            subprocess.run(
                ["icacls", str(COOKIES_FILE), "/inheritance:r",
                 "/grant:r", f"{os.environ.get('USERNAME', '')}:F"],
                capture_output=True, check=False,
            )
        else:
            os.chmod(COOKIES_FILE, 0o600)
    except Exception:
        pass


def _load_cookies_from_file() -> Optional[requests.cookies.RequestsCookieJar]:
    if not COOKIES_FILE.exists():
        return None
    _restrict_cookie_file_permissions()
    try:
        with open(COOKIES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if "sessionid" not in data or "steamLoginSecure" not in data:
            logger.warning(f"{COOKIES_FILE} existe pero le faltan claves sessionid/steamLoginSecure")
            return None
        jar = requests.cookies.RequestsCookieJar()
        for k, v in data.items():
            jar.set(k, v, domain=".steamcommunity.com", path="/")
        return jar
    except Exception as e:
        logger.warning(f"No se pudo leer {COOKIES_FILE}: {e}")
        return None


def _get_cached_cookies() -> Tuple[str, Optional[requests.cookies.RequestsCookieJar]]:
    """Carga cookies 1 sola vez y cachea (source, jar)."""
    global _COOKIES_CACHE
    if _COOKIES_CACHE is not None:
        return _COOKIES_CACHE
    for _loader, _src in [
        (_load_cookies_from_firefox, "firefox"),
        (_load_cookies_from_chrome, "chrome"),
        (_load_cookies_from_edge, "edge"),
    ]:
        jar = _loader()
        if jar is not None:
            _COOKIES_CACHE = (_src, jar)
            return _COOKIES_CACHE
    jar = _load_cookies_from_file()
    if jar is not None:
        _COOKIES_CACHE = ("file", jar)
        return _COOKIES_CACHE
    return ("none", None)


def invalidate_cookies_cache() -> None:
    global _COOKIES_CACHE
    _COOKIES_CACHE = None


def cookies_configured() -> bool:
    return _get_cached_cookies()[1] is not None


def cookies_source() -> str:
    return _get_cached_cookies()[0]


def _bootstrap_sessionid(s: requests.Session) -> bool:
    """Si no hay sessionid, visita steamcommunity.com para que Steam lo emita."""
    if s.cookies.get("sessionid", domain=".steamcommunity.com") or s.cookies.get("sessionid"):
        return True
    try:
        r = s.get("https://steamcommunity.com/my/home/", timeout=20, allow_redirects=True)
        r.raise_for_status()
        if s.cookies.get("sessionid", domain=".steamcommunity.com") or s.cookies.get("sessionid"):
            return True
    except Exception as e:
        logger.warning(f"Bootstrap de sessionid fallo: {e}")
    return False


def _session() -> Optional[requests.Session]:
    _, jar = _get_cached_cookies()
    if jar is None:
        return None
    s = requests.Session()
    s.cookies = jar
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0",
        "Origin": "https://steamcommunity.com",
        "Referer": UPLOAD_URL,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "X-Requested-With": "XMLHttpRequest",
    })
    _bootstrap_sessionid(s)
    return s


# ---------------------------------------------------------------------------
# Parsing de respuesta
# ---------------------------------------------------------------------------

_PUBID_REDIRECT_RE = re.compile(r'[?&]id=(\d{6,})')
_PUBID_JSON_RE = re.compile(r'"publishedfileid"\s*:\s*"?(\d{6,})"?')


def _extract_publishedfileid(resp: requests.Response) -> Optional[str]:
    # 1) Redirect de éxito: /filedetails/?id=<pubid>
    for r in list(resp.history) + [resp]:
        loc = r.headers.get("Location", "")
        m = _PUBID_REDIRECT_RE.search(loc)
        if m:
            return m.group(1)
    # 2) URL final (allow_redirects=True)
    m = _PUBID_REDIRECT_RE.search(resp.url or "")
    if m:
        return m.group(1)
    # 3) JSON body
    try:
        j = resp.json()
        if j.get("success") == 1:
            pid = j.get("publishedfileid")
            if pid:
                return str(pid)
    except ValueError:
        pass
    # 4) Fallback JSON regex en HTML
    m = _PUBID_JSON_RE.search(resp.text or "")
    if m:
        return m.group(1)
    return None


def _looks_like_login_page(text: str) -> bool:
    low = text.lower() if text else ""
    return "g_sessionid" not in low and ("login" in low or "sign in" in low)


# ---------------------------------------------------------------------------
# Part-number parsing (sync título con sufijo real del archivo)
# ---------------------------------------------------------------------------

_PART_NUM_RE = re.compile(r"_part[_\-]?(\d+)", re.IGNORECASE)
_TRAILING_NUM_RE = re.compile(r"(\d+)(?=\.[^.]+$)")


def _parse_part_number(path: Path) -> Optional[int]:
    """Extrae el número de parte del nombre del archivo.
    Prioriza `_part_N` / `_partN` / `_part-N`; fallback: número final antes de la extensión."""
    name = path.name
    m = _PART_NUM_RE.search(name)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            pass
    m = _TRAILING_NUM_RE.search(name)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            pass
    return None


def _sort_by_part(file_paths: List[Path]) -> List[Path]:
    """Ordena por número de parte. main antes que side para el mismo número."""
    def _key(p: Path):
        n = _parse_part_number(p)
        name = p.name.lower()
        is_side = "side" in name
        return (n is None, n if n is not None else 0, is_side, name)
    return sorted(file_paths, key=_key)


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------

def _upload_single(session: requests.Session, file_path: Path, title: str,
                   description: str = "") -> Tuple[bool, str]:
    sessionid = session.cookies.get("sessionid", domain=".steamcommunity.com") \
                or session.cookies.get("sessionid")
    if not sessionid:
        return False, "sessionid no encontrado en cookies"

    # Hard-check: Steam artwork showcase límite = 5 MiB exactos (5242880 bytes).
    # Detectar antes para no gastar round-trip.
    STEAM_MAX_BYTES = 5 * 1024 * 1024  # 5,242,880
    try:
        file_size = file_path.stat().st_size
    except OSError as e:
        return False, f"No stat: {e}"
    if file_size > STEAM_MAX_BYTES:
        return False, (f"Archivo {file_size:,} bytes > límite Steam "
                       f"{STEAM_MAX_BYTES:,} bytes ({STEAM_MAX_BYTES/1024/1024:.2f} MiB). "
                       f"Reoptimiza con Optimizar a 5MB")

    # El form real manda el archivo dos veces: 'file' y 'preview_file'
    try:
        file_bytes = file_path.read_bytes()
    except OSError as e:
        return False, f"No se pudo leer el archivo: {e}"

    _ext = file_path.suffix.lower()
    if _ext == '.gif':
        mime_type = "image/gif"
        try:
            if file_bytes and file_bytes[-1] != 0x21:
                file_bytes = file_bytes[:-1] + b"\x21"
        except Exception:
            pass
    elif _ext in ('.jpg', '.jpeg'):
        mime_type = "image/jpeg"
    else:
        mime_type = "image/png"

    try:
        from PIL import Image as _PIL_Image
        with _PIL_Image.open(file_path) as _im:
            img_w, img_h = _im.size
    except Exception as e:
        return False, f"Imagen corrupta o ilegible: {e}"

    # Scrape form real de /sharedfiles/uploadartwork para obtener action + hidden fields
    form_action = SUBMIT_URL
    form_fields: Dict[str, str] = {}
    try:
        r_form = session.get(UPLOAD_URL, timeout=30)
        r_form.raise_for_status()
        html = r_form.text
        # dump uploadartwork GET para inspección (rotado)
        try:
            LOGS_DIR.mkdir(exist_ok=True)
            (LOGS_DIR / f"uploadartwork_get_{int(time.time())}.html").write_text(
                _redact_sensitive(html), encoding="utf-8", errors="ignore")
            _rotate_logs()
        except Exception:
            pass
        # action
        m_action = re.search(r'<form[^>]+id=["\']ImageForm["\'][^>]*action=["\']([^"\']+)["\']', html, re.I)
        if not m_action:
            m_action = re.search(r'<form[^>]+action=["\']([^"\']*submititem[^"\']*)["\']', html, re.I)
        if m_action:
            act = m_action.group(1)
            form_action = act if act.startswith("http") else f"https://steamcommunity.com{act}"
        # hidden inputs
        for m_h in re.finditer(
            r'<input[^>]+type=["\']hidden["\'][^>]+name=["\']([^"\']+)["\'][^>]+value=["\']([^"\']*)["\']',
            html, re.I,
        ):
            form_fields[m_h.group(1)] = m_h.group(2)
        # Algunos inputs vienen con value antes de name — orden invertido
        for m_h in re.finditer(
            r'<input[^>]+type=["\']hidden["\'][^>]+value=["\']([^"\']*)["\'][^>]+name=["\']([^"\']+)["\']',
            html, re.I,
        ):
            form_fields.setdefault(m_h.group(2), m_h.group(1))
    except Exception:
        pass

    # Mezcla: hidden fields del form manda (wg/wg_hmac/token/sessionid); solo
    # sobreescribimos lo user-supplied.
    data = dict(form_fields)
    data["title"] = title[:128]
    data["description"] = description
    data["visibility"] = VISIBILITY
    # Dimensiones: el form trae "0", sobreescribir siempre con las reales
    if img_w > 0:
        data["image_width"] = str(img_w)
    if img_h > 0:
        data["image_height"] = str(img_h)
    # Confiamos en los hidden fields del form (appid=767, consumer_app_id=767,
    # file_type y tokens). Solo defaults si el form no los trajo.
    data.setdefault("appid", WORKSHOP_APP_ID)
    data.setdefault("consumer_app_id", CONSUMER_APP_ID)
    data.setdefault("file_type", FILE_TYPE)
    data.setdefault("tags", "")
    data.setdefault("youtube_username", "")
    files = {
        "file": (file_path.name, file_bytes, mime_type),
        "preview_file": (file_path.name, file_bytes, mime_type),
    }

    # Un retry con backoff para transient 429/5xx
    last_err = ""
    for attempt in range(3):
        try:
            resp = session.post(form_action, data=data, files=files, timeout=120)
        except requests.RequestException as e:
            last_err = f"Error de red: {e}"
            time.sleep(2)
            continue

        if resp.status_code in (429, 500, 502, 503, 504):
            last_err = f"HTTP {resp.status_code} (reintentando)"
            time.sleep(3 * (attempt + 1))
            continue

        if resp.status_code not in (200, 302):
            return False, f"HTTP {resp.status_code}"

        if _looks_like_login_page(resp.text):
            return False, ("Sesión expirada: re-logueate en Steam desde Firefox, Chrome o Edge, "
                           "o re-exporta steam_cookies.json")

        pubid = _extract_publishedfileid(resp)
        if pubid:
            return True, f"OK (id={pubid})"

        # Dump respuesta para depuración (rotado)
        try:
            LOGS_DIR.mkdir(exist_ok=True)
            dump_file = LOGS_DIR / f"upload_fail_{int(time.time())}.html"
            dump_file.write_text(_redact_sensitive(resp.text or ""), encoding="utf-8", errors="ignore")
            _rotate_logs()
            dump_hint = f" (dump: {dump_file})"
        except Exception:
            dump_hint = ""

        # Sin id claro: puede ser LimitExceeded o rechazo
        snippet = (resp.text or "")[:300].replace("\n", " ")
        final_url = resp.url
        try:
            fg_url = r_form.url
            fg_status = r_form.status_code
            fg_size = len(r_form.text or "")
        except Exception:
            fg_url, fg_status, fg_size = "?", "?", 0
        _posted_keys = list(data.keys())
        _posted_preview = {k: (v[:40] + "...") if isinstance(v, str) and len(v) > 40 else v
                           for k, v in data.items()
                           if k in ("appid", "consumer_app_id", "file_type",
                                    "visibility", "image_width", "image_height",
                                    "publishedfileid", "id", "realm", "redirect_uri")}
        fields_info = (f"action={form_action} hidden={list(form_fields.keys())} "
                       f"GET_form: url={fg_url} status={fg_status} size={fg_size} "
                       f"posted_keys={_posted_keys} posted_preview={_posted_preview}")
        return False, (f"Steam no devolvió publishedfileid. "
                       f"URL final: {final_url} | status: {resp.status_code}{dump_hint}. "
                       f"Form: {fields_info}. Snippet: {snippet}")

    return False, last_err or "Error desconocido"


def upload_fragments(file_paths: List[Path],
                     title_prefix: str = "WorkshopArt",
                     progress_cb: Optional[Callable[[int, int, str], None]] = None
                     ) -> List[Tuple[Path, bool, str]]:
    session = _session()
    if session is None:
        return [(p, False, "Cookies no disponibles (Firefox, Chrome, Edge ni steam_cookies.json)") for p in file_paths]

    file_paths = _sort_by_part(list(file_paths))
    results: List[Tuple[Path, bool, str]] = []
    total = len(file_paths)
    _MAX_FRAG_TRIES = 3
    for i, path in enumerate(file_paths, 1):
        part_num = _parse_part_number(path) or i
        title = f"{title_prefix} - {part_num}/{total}"
        ok, msg = False, "Sin intentar"
        for _attempt in range(1, _MAX_FRAG_TRIES + 1):
            _hint = f" [intento {_attempt}/{_MAX_FRAG_TRIES}]" if _attempt > 1 else ""
            if progress_cb:
                progress_cb(i, total,
                            f"Subiendo {path.name} ({part_num}/{total}){_hint}...")
            ok, msg = _upload_single(session, path, title)
            if ok:
                break
            _is_session = "expirada" in msg.lower() or "re-logu" in msg.lower()
            if _is_session or _attempt == _MAX_FRAG_TRIES:
                break
            if progress_cb:
                progress_cb(i, total,
                            f"[RETRY {_attempt}/{_MAX_FRAG_TRIES}] {path.name}: {msg}")
            time.sleep(3 * _attempt)
        results.append((path, ok, msg))
        if progress_cb:
            status = "OK" if ok else "FAIL"
            progress_cb(i, total, f"[{status}] {path.name} ({part_num}/{total}): {msg}")
        if i < total:
            time.sleep(UPLOAD_DELAY_SEC)
    return results


# ---------------------------------------------------------------------------
# Playwright — automatiza Firefox visible, mimica al usuario real
# ---------------------------------------------------------------------------

def _find_system_firefox() -> Optional[str]:
    """Devuelve la ruta al firefox.exe del sistema, o None si no se encuentra."""
    _pf = os.environ.get("ProgramFiles", r"C:\Program Files")
    _pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    candidates = [
        str(Path(_pf) / "Mozilla Firefox" / "firefox.exe"),
        str(Path(_pf86) / "Mozilla Firefox" / "firefox.exe"),
    ]
    # Buscar en registro de Windows
    try:
        import winreg
        for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            for subkey in (
                r"SOFTWARE\Mozilla\Mozilla Firefox",
                r"SOFTWARE\WOW6432Node\Mozilla\Mozilla Firefox",
            ):
                try:
                    with winreg.OpenKey(root, subkey) as k:
                        version, _ = winreg.QueryValueEx(k, "CurrentVersion")
                        with winreg.OpenKey(k, f"{version}\\Main") as mk:
                            path, _ = winreg.QueryValueEx(mk, "PathToExe")
                            if path and Path(path).exists():
                                return str(path)
                except OSError:
                    pass
    except Exception:
        pass
    for c in candidates:
        if Path(c).exists():
            return c
    return None


def _pw_cookies_from_jar(jar: requests.cookies.RequestsCookieJar) -> list:
    out = []
    for c in jar:
        dom = c.domain or ".steamcommunity.com"
        if "steam" not in dom.lower():
            continue
        rest = getattr(c, "_rest", {}) or {}
        # Normalizar sameSite para playwright: "Strict" | "Lax" | "None"
        ss_raw = (rest.get("SameSite") or rest.get("samesite") or "").strip().lower()
        if ss_raw in ("none",):
            same_site = "None"
        elif ss_raw in ("strict",):
            same_site = "Strict"
        else:
            same_site = "Lax"
        # Steam: steamLoginSecure normalmente SameSite=None + Secure
        if c.name == "steamLoginSecure":
            same_site = "None"
        cookie = {
            "name": c.name,
            "value": c.value,
            "domain": dom,
            "path": c.path or "/",
            "secure": True if c.name == "steamLoginSecure" else bool(c.secure),
            "httpOnly": bool(rest.get("HttpOnly") or rest.get("httponly")) or False,
            "sameSite": same_site,
        }
        if getattr(c, "expires", None):
            try:
                cookie["expires"] = int(c.expires)
            except (TypeError, ValueError):
                pass
        out.append(cookie)
    return out


def upload_fragments_playwright(file_paths: List[Path],
                                title_prefix: str = "WorkshopArt",
                                headless: bool = False,
                                mode: str = "artwork",
                                workshop_appid: str = "480",
                                spoof_dimensions: bool = False,
                                pubids: List[str] = None,
                                progress_cb: Optional[Callable[[int, int, str], None]] = None
                                ) -> List[Tuple[Path, bool, str]]:
    """Sube vía Playwright: abre Firefox controlado, inyecta cookies de tu
    Firefox real, rellena el form y hace click. Mucho más fiable que HTTP puro."""
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    except ImportError:
        return [(p, False,
                 "Playwright no instalado. Ejecuta: "
                 "pip install playwright && playwright install firefox")
                for p in file_paths]

    _, jar = _get_cached_cookies()
    if jar is None:
        return [(p, False, "Cookies no disponibles") for p in file_paths]
    pw_cookies = _pw_cookies_from_jar(jar)

    file_paths = _sort_by_part(list(file_paths))
    results: List[Tuple[Path, bool, str]] = []
    total = len(file_paths)

    with sync_playwright() as pw:
        # Playwright Firefox requiere su propio build con soporte juggler-pipe.
        # El Firefox del sistema NO es compatible aunque esté instalado.
        def _launch_browser():
            return pw.firefox.launch(headless=headless)

        def _install_firefox_browser():
            """Instala el Firefox de Playwright.
            Opcion 0 (primaria): descarga directa del zip desde CDN de Playwright,
            no requiere node.exe ni Python externo.
            Opciones 1/3 como fallback por si el CDN no esta disponible."""
            import subprocess as _sub
            import shutil as _sh
            import zipfile as _zipfile

            if progress_cb:
                progress_cb(0, len(file_paths),
                            "Descargando Firefox (~80 MB, solo la primera vez)...")

            _install_log = _PW_BROWSERS_DIR.parent / "logs" / "playwright_install.log"
            _install_log.parent.mkdir(parents=True, exist_ok=True)

            def _log(msg: str):
                try:
                    with open(_install_log, 'a', encoding='utf-8') as _lf:
                        _lf.write(msg + "\n")
                except Exception:
                    pass
                if progress_cb:
                    progress_cb(0, len(file_paths), f"  {msg}")

            # ------------------------------------------------------------------
            # Opcion 0: descarga directa desde CDN (sin node.exe, sin Python)
            # ------------------------------------------------------------------
            try:
                # Leer revision desde browsers.json del paquete playwright.
                # Fallback hardcoded = 1509 (Firefox 146.0.1, la version actual).
                _revision = "1509"
                _bjson_candidates = []
                if getattr(sys, 'frozen', False):
                    _meipass = getattr(sys, '_MEIPASS', None)
                    if _meipass:
                        _bjson_candidates.append(
                            Path(_meipass) / "playwright" / "driver" / "package" / "browsers.json")
                try:
                    import playwright as _pw_pkg
                    _bjson_candidates.append(
                        Path(_pw_pkg.__file__).parent / "driver" / "package" / "browsers.json")
                except Exception:
                    pass

                for _bjson in _bjson_candidates:
                    if _bjson.exists():
                        try:
                            _bdata = json.loads(_bjson.read_text(encoding='utf-8'))
                            for _browser in _bdata.get('browsers', []):
                                if _browser.get('name') == 'firefox':
                                    _rev_raw = (
                                        _browser.get('revision')
                                        or _browser.get('browserVersion')
                                        or (_browser.get('revisionOverrides') or {}).get('win64')
                                    )
                                    if _rev_raw:
                                        _revision = str(_rev_raw)
                                    break
                        except Exception:
                            pass
                        break

                _log(f"Firefox revision: {_revision}")
                _target_dir = _PW_BROWSERS_DIR / f"firefox-{_revision}"
                _ff_exe = _target_dir / "firefox" / "firefox.exe"

                if _ff_exe.exists():
                    _log(f"Firefox ya instalado: {_ff_exe}")
                    return True

                _cdn_urls = [
                    f"https://cdn.playwright.dev/dbazure/download/playwright/builds/firefox/{_revision}/firefox-win64.zip",
                    f"https://playwright.download.prss.microsoft.com/dbazure/download/playwright/builds/firefox/{_revision}/firefox-win64.zip",
                    f"https://cdn.playwright.dev/builds/firefox/{_revision}/firefox-win64.zip",
                ]

                _temp_zip = _PW_BROWSERS_DIR.parent / "temp" / f"firefox-{_revision}.zip"
                _temp_zip.parent.mkdir(parents=True, exist_ok=True)

                _downloaded = False
                for _url in _cdn_urls:
                    try:
                        _host = _url.split('/')[2]
                        _log(f"Descargando desde {_host}...")
                        _r = requests.get(_url, stream=True, timeout=120)
                        _r.raise_for_status()
                        _total = int(_r.headers.get('content-length', 0))
                        _dl = 0
                        _last_pct = -1
                        with open(_temp_zip, 'wb') as _f:
                            for _chunk in _r.iter_content(chunk_size=65536):
                                if _chunk:
                                    _f.write(_chunk)
                                    _dl += len(_chunk)
                                    if _total > 0:
                                        _pct = int(_dl / _total * 100 / 10) * 10
                                        if _pct != _last_pct:
                                            _last_pct = _pct
                                            _log(f"Firefox {_pct}% "
                                                 f"({_dl//1024//1024} / {_total//1024//1024} MB)")
                        _downloaded = True
                        _log("Descarga completada")
                        break
                    except Exception as _ex:
                        _log(f"CDN {_host} fallo: {_ex}")
                        try:
                            _temp_zip.unlink()
                        except Exception:
                            pass

                if _downloaded:
                    # No hay checksum publico por-revision para builds de Playwright (cambian
                    # por version). Mitigacion: solo se descarga de dominios oficiales de
                    # Microsoft/Playwright (lista fija arriba, todos HTTPS) y se valida que el
                    # zip no este corrupto antes de extraer.
                    try:
                        with _zipfile.ZipFile(_temp_zip, 'r') as _zf_check:
                            _bad = _zf_check.testzip()
                            if _bad is not None:
                                raise ValueError(f"zip corrupto, entrada invalida: {_bad}")
                    except Exception as _integrity_ex:
                        _log(f"Descarga de Firefox invalida, descartada: {_integrity_ex}")
                        try:
                            _temp_zip.unlink()
                        except Exception:
                            pass
                        _downloaded = False

                if _downloaded:
                    _target_dir.mkdir(parents=True, exist_ok=True)
                    _log(f"Extrayendo en {_target_dir}...")
                    with _zipfile.ZipFile(_temp_zip, 'r') as _zf:
                        _zf.extractall(_target_dir)
                    try:
                        _temp_zip.unlink()
                    except Exception:
                        pass

                    if _ff_exe.exists():
                        # Crear markers que playwright usa para validar la instalacion
                        for _marker in ("DEPENDENCIES_VALIDATED", "INSTALLATION_COMPLETE"):
                            try:
                                (_target_dir / _marker).touch()
                            except Exception:
                                pass
                        _log(f"Firefox listo: {_ff_exe}")
                        return True

                    # El zip puede tener una carpeta raiz extra — buscar y reubicar
                    _found_exes = list(_target_dir.rglob("firefox.exe"))
                    _log(f"firefox.exe encontrado en: {_found_exes}")
                    if _found_exes:
                        _actual_parent = _found_exes[0].parent
                        _expected_parent = _target_dir / "firefox"
                        if _actual_parent != _expected_parent:
                            try:
                                _sh.move(str(_actual_parent), str(_expected_parent))
                                _log(f"Reubicado a {_expected_parent}")
                                if _ff_exe.exists():
                                    for _marker in ("DEPENDENCIES_VALIDATED", "INSTALLATION_COMPLETE"):
                                        try:
                                            (_target_dir / _marker).touch()
                                        except Exception:
                                            pass
                                    return True
                            except Exception as _mv_ex:
                                _log(f"Error reubicando: {_mv_ex}")
                    _log("AVISO: firefox.exe no encontrado tras extraccion")
            except Exception as _e0:
                _log(f"Opcion 0 (descarga directa) fallo: {_e0}")

            # ------------------------------------------------------------------
            # Opcion 1: playwright._impl._driver API (node.exe bundleado)
            # ------------------------------------------------------------------
            def _run_install(cmd, env=None):
                try:
                    _e = env or os.environ.copy()
                    _e['PLAYWRIGHT_BROWSERS_PATH'] = str(_PW_BROWSERS_DIR)
                    r = _sub.run(cmd, env=_e, capture_output=True, timeout=420,
                                 encoding='utf-8', errors='replace')
                    _out = (r.stdout or '') + (r.stderr or '')
                    _log(f"cmd={cmd} rc={r.returncode}")
                    for _line in (_out.strip().splitlines() or [])[-5:]:
                        _log(f"  {_line}")
                    return r.returncode == 0
                except Exception as _ex:
                    _log(f"cmd={cmd} EXCEPTION: {_ex}")
                    return False

            try:
                import playwright._impl._driver as _pw_drv
                if hasattr(_pw_drv, 'compute_driver_executable') and hasattr(_pw_drv, 'get_driver_env'):
                    _drv_result = _pw_drv.compute_driver_executable()
                    _drv_env = _pw_drv.get_driver_env()
                    if isinstance(_drv_result, tuple):
                        _node_exe, _cli_js = _drv_result
                        _install_cmd = [str(_node_exe), str(_cli_js), 'install', 'firefox']
                    else:
                        _install_cmd = [str(_drv_result), 'install', 'firefox']
                    if _run_install(_install_cmd, env=_drv_env):
                        return True
            except Exception as _ex:
                _log(f"playwright driver API: {_ex}")

            # ------------------------------------------------------------------
            # Opcion 3: Python real en PATH
            # ------------------------------------------------------------------
            for _cmd in ("python", "python3", "py"):
                _py = _sh.which(_cmd)
                if _py and Path(_py).resolve() != Path(sys.executable).resolve():
                    if _run_install([_py, "-m", "playwright", "install", "firefox"]):
                        return True

            _log(f"Todas las opciones fallaron. Log: {_install_log}")
            return False

        def _install_and_launch():
            ok = _install_firefox_browser()
            if not ok and progress_cb:
                progress_cb(0, len(file_paths),
                            "Advertencia: instalacion automatica fallo, intentando arrancar igualmente...")
            return pw.firefox.launch(headless=headless)

        try:
            browser = _launch_browser()
        except Exception as _launch_err:
            err_msg = str(_launch_err)
            needs_install = (
                "Executable doesn't exist" in err_msg
                or "playwright install" in err_msg
                or "Failed to launch" in err_msg
                or "juggler" in err_msg.lower()
            )
            if needs_install:
                try:
                    browser = _install_and_launch()
                except Exception as _e2:
                    return [(p, False,
                             f"No se pudo iniciar el navegador: {_e2}. "
                             "Ejecuta manualmente: playwright install firefox")
                            for p in file_paths]
            else:
                raise
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0"
        )
        try:
            context.add_cookies(pw_cookies)
        except Exception as e:
            browser.close()
            return [(p, False, f"No se pudieron inyectar cookies: {e}") for p in file_paths]

        page = context.new_page()

        # Capturar alerts/errores JS de Steam (SubmitItem() aborta con alert
        # si el usuario no marca 'agree_terms' o si falta algún campo).
        dialog_messages: list[str] = []
        def _on_dialog(d):
            try:
                dialog_messages.append(f"{d.type}: {d.message}")
                d.dismiss()
            except Exception:
                pass
        try:
            page.on("dialog", _on_dialog)
            page.on("pageerror", lambda e: dialog_messages.append(f"pageerror: {e}"))
            page.on("console", lambda m: (
                dialog_messages.append(f"console.{m.type}: {m.text}")
                if m.type in ("error", "warning") else None))
        except Exception:
            pass

        # Verificar sesión ANTES de iniciar loop. Si no estamos logueados,
        # abortar con mensaje claro en vez de "browser abre y no hace nada".
        try:
            page.goto("https://steamcommunity.com/my/", wait_until="domcontentloaded", timeout=25000)
            cur_url = page.url
            page_title = ""
            try:
                page_title = page.title() or ""
            except Exception:
                pass
            logged_in = ("/id/" in cur_url or "/profiles/" in cur_url) and "login" not in cur_url.lower()
            if progress_cb:
                progress_cb(0, total, f"Sesión check: url={cur_url} title={page_title[:60]}")
            if not logged_in:
                try:
                    LOGS_DIR.mkdir(exist_ok=True)
                    shot = LOGS_DIR / f"pw_login_check_{int(time.time())}.png"
                    page.screenshot(path=str(shot), full_page=True)
                except Exception:
                    shot = None
                msg = (f"Sesión no activa. Steam redirigió a {cur_url}. "
                       f"Re-loguéate en Firefox y CIÉRRALO antes de subir, o "
                       f"re-exporta steam_cookies.json.")
                if shot:
                    msg += f" (screenshot: {shot})"
                browser.close()
                return [(p, False, msg) for p in file_paths]
        except Exception as e:
            if progress_cb:
                progress_cb(0, total, f"⚠️ No se pudo verificar sesión: {e} (continuando igualmente)")

        # JS que fija los hidden fields y DEVUELVE los valores leídos de vuelta
        # para verificar que realmente se aplicaron.
        js_apply = (
            "(cfg) => {"
            " const set = (n, v) => { const el = document.querySelector('[name=\"' + n + '\"]');"
            "   if (!el) return null;"
            "   el.value = v;"
            "   el.dispatchEvent(new Event('change', {bubbles:true}));"
            "   return el.value; };"
            " return {"
            "   consumer_app_id: set('consumer_app_id', cfg.appid),"
            "   file_type:       set('file_type', cfg.file_type),"
            "   visibility:      set('visibility', '0'),"
            " };"
            "}"
        )

        # Copia a temp con nombre CORTO (evita MAX_PATH 260 en Windows, que rompe
        # el protocolo Firefox→Playwright en set_input_files) y aplica trailer patch
        # (0x3B → 0x21) si hace falta.
        def _ensure_trailer_patch(p: Path, idx: int) -> Path:
            try:
                with open(p, "rb") as f:
                    data = f.read()
                if not data:
                    return p
                if p.suffix.lower() == '.gif' and data[-1] != 0x21:
                    data = data[:-1] + b"\x21"
                LOGS_DIR.mkdir(exist_ok=True)
                short = LOGS_DIR / f"up_{int(time.time())}_{idx}{p.suffix.lower()}"
                short.write_bytes(data)
                return short
            except Exception:
                return p

        _MAX_FRAG_TRIES = 3
        for i, path in enumerate(file_paths, 1):
            part_num = _parse_part_number(path) or i
            title = f"{title_prefix} - {part_num}/{total}"
            _frag_appended = False

            for _try in range(1, _MAX_FRAG_TRIES + 1):
                _hint = f" [intento {_try}/{_MAX_FRAG_TRIES}]" if _try > 1 else ""
                if _try > 1:
                    if progress_cb:
                        progress_cb(i, total, f"Reintentando {path.name}{_hint}...")
                    time.sleep(3 * _try)
                if progress_cb:
                    progress_cb(i, total,
                                f"Subiendo {path.name} ({part_num}/{total}){_hint}...")
                try:
                    upload_path = _ensure_trailer_patch(path, i)
                    if path.suffix.lower() == '.gif':
                        with open(upload_path, "rb") as _f:
                            _f.seek(-1, 2)
                            last_byte = _f.read(1)
                        if progress_cb:
                            trailer_ok = last_byte == b"\x21"
                            progress_cb(i, total,
                                        f"   trailer byte: 0x{last_byte.hex().upper()} "
                                        f"{'(OK)' if trailer_ok else '(NO patcheado!)'}")
                    pubid = (pubids[i - 1] if pubids and i - 1 < len(pubids) else None)
                    if pubid:
                        form_url = f"https://steamcommunity.com/sharedfiles/edititem/767/3/{pubid}/"
                        if progress_cb:
                            progress_cb(i, total, f"   editando item existente id={pubid}")
                    else:
                        form_url = "https://steamcommunity.com/sharedfiles/edititem/767/3/"
                    page.goto(form_url, wait_until="domcontentloaded", timeout=30000)
                    try:
                        page.wait_for_load_state("networkidle", timeout=15000)
                    except Exception:
                        pass
                    final_url_form = page.url
                    if "login" in final_url_form.lower():
                        try:
                            LOGS_DIR.mkdir(exist_ok=True)
                            shot = LOGS_DIR / f"pw_redir_login_{int(time.time())}.png"
                            page.screenshot(path=str(shot), full_page=True)
                        except Exception:
                            shot = None
                        raise Exception(f"Sesión expirada o cookies inválidas: Steam redirigió a login. "
                                        f"Re-logéate en Firefox/Chrome/Edge y cierra el navegador antes de subir."
                                        + (f" screenshot={shot}" if shot else ""))
                    if progress_cb:
                        progress_cb(i, total, f"   form URL: {final_url_form}")

                    if mode == "workshop":
                        cfg = {"appid": workshop_appid, "file_type": "0"}
                    elif mode == "screenshot":
                        cfg = {"appid": "767", "file_type": "5"}
                    else:
                        cfg = {"appid": "767", "file_type": "3"}
                    if mode in ("workshop", "screenshot"):
                        applied_pre = page.evaluate(js_apply, cfg)
                        if progress_cb:
                            progress_cb(i, total,
                                        f"   hidden fields (pre-upload): {applied_pre}")

                    try:
                        page.evaluate(
                            "() => {"
                            " document.querySelectorAll('input[type=file]').forEach(el => {"
                            "   el.style.display='block'; el.style.visibility='visible';"
                            "   el.style.opacity='1'; el.style.width='200px'; el.style.height='30px';"
                            "   el.style.position='static'; el.style.pointerEvents='auto';"
                            "   el.hidden=false; el.disabled=false; el.removeAttribute('hidden');"
                            " });"
                            "}"
                        )
                    except Exception:
                        pass

                    file_inputs = page.locator("input[type='file']")
                    if file_inputs.count() == 0:
                        try:
                            LOGS_DIR.mkdir(exist_ok=True)
                            shot = LOGS_DIR / f"pw_no_fileinput_{int(time.time())}.png"
                            page.screenshot(path=str(shot), full_page=True)
                            dump = LOGS_DIR / f"pw_no_fileinput_{int(time.time())}.html"
                            dump.write_text(_redact_sensitive(page.content()), encoding="utf-8", errors="ignore")
                        except Exception:
                            shot = dump = None
                        raise Exception(
                            f"No se encontró input[type=file] en {final_url_form}. "
                            f"Probable: sesión caducada o Steam cambió el form."
                            + (f" screenshot={shot}" if shot else "")
                            + (f" html={dump}" if dump else ""))

                    def _set_files(selector: str) -> bool:
                        try:
                            handle = page.query_selector(selector)
                            if handle is None:
                                return False
                            handle.set_input_files(str(upload_path))
                            return True
                        except Exception as e:
                            if progress_cb:
                                progress_cb(i, total, f"   set_input_files({selector}) fallo: {e}")
                            return False

                    primary_ok = (_set_files("input#file")
                                  or _set_files("input[name='file']")
                                  or _set_files("input[type='file']"))
                    if not primary_ok:
                        raise Exception("set_input_files falló en todos los selectores")
                    if file_inputs.count() > 1:
                        _set_files("input[name='preview_file']") or _set_files("#preview_file")

                    for sel in ["#title", "input[name='title']", "textarea[name='title']"]:
                        loc = page.locator(sel)
                        if loc.count() > 0:
                            loc.first.fill(title)
                            break

                    page.wait_for_timeout(3000)

                    if mode in ("artwork", "screenshot"):
                        try:
                            from PIL import Image as _PilImg
                            with _PilImg.open(upload_path) as _im:
                                _actual_w, _actual_h = _im.size
                            _dim_w = 1000 if spoof_dimensions else _actual_w
                            _dim_h = 1    if spoof_dimensions else _actual_h
                            spoofed = page.evaluate(
                                f"() => {{"
                                f" const w = document.querySelector('[name=image_width]');"
                                f" const h = document.querySelector('[name=image_height]');"
                                f" if (w) w.value = '{_dim_w}';"
                                f" if (h) h.value = '{_dim_h}';"
                                f" return {{w: w ? w.value : null, h: h ? h.value : null}};"
                                f"}}"
                            )
                            if progress_cb:
                                progress_cb(i, total, f"   dims → {spoofed}")
                        except Exception:
                            pass

                    checked = False
                    for sel in [
                        "input#agree_terms",
                        "input[name='agree_terms']",
                        "input#rightsAttested",
                        "input[name='rightsAttested']",
                        "input#agreementCheck",
                        "input[name='agreementCheck']",
                        "input[type='checkbox'][name*='rights' i]",
                        "input[type='checkbox'][name*='agree' i]",
                        "input[type='checkbox'][id*='rights' i]",
                        "input[type='checkbox'][id*='agree' i]",
                    ]:
                        loc = page.locator(sel)
                        if loc.count() > 0:
                            try:
                                loc.first.check(force=True)
                                checked = True
                                break
                            except Exception:
                                try:
                                    loc.first.evaluate("el => el.checked = true")
                                    loc.first.dispatch_event("change")
                                    checked = True
                                    break
                                except Exception:
                                    pass
                    if not checked:
                        all_cbs = page.locator("input[type='checkbox']")
                        for idx in range(all_cbs.count()):
                            try:
                                all_cbs.nth(idx).check(force=True)
                                checked = True
                            except Exception:
                                try:
                                    all_cbs.nth(idx).evaluate(
                                        "el => { el.checked = true; "
                                        "el.dispatchEvent(new Event('change', {bubbles:true})); }")
                                    checked = True
                                except Exception:
                                    pass
                    if progress_cb:
                        progress_cb(i, total,
                                    f"   checkbox: {'OK' if checked else 'NO encontrado'}")

                    if mode in ("workshop", "screenshot"):
                        applied_post = page.evaluate(js_apply, cfg)
                        if progress_cb:
                            progress_cb(i, total,
                                        f"   hidden fields (pre-submit): {applied_post}")
                        expected = {
                            "consumer_app_id": str(cfg["appid"]),
                            "file_type": str(cfg["file_type"]),
                        }
                        mismatch = {k: (applied_post.get(k), v)
                                    for k, v in expected.items()
                                    if str(applied_post.get(k)) != v}
                        if mismatch and progress_cb:
                            progress_cb(i, total,
                                        f"   ⚠️  MISMATCH hidden fields: {mismatch}")

                    dialog_messages.clear()
                    clicked = False
                    try:
                        has_submit_item = page.evaluate(
                            "() => typeof SubmitItem === 'function'")
                        if has_submit_item:
                            page.evaluate("() => { try { SubmitItem(false); } catch(e) { "
                                          "console.error('SubmitItem err:', e); } }")
                            clicked = True
                            if progress_cb:
                                progress_cb(i, total, "   submit via SubmitItem(false)")
                    except Exception as e:
                        if progress_cb:
                            progress_cb(i, total, f"   SubmitItem eval fallo: {e}")
                    if not clicked:
                        for sel in ["#submitAssetButton", "input[type='submit']",
                                    "button[type='submit']", "#btnSubmitAsset",
                                    "a.btn_green_steamui:has-text('Save')",
                                    "a:has-text('Save and Continue')"]:
                            loc = page.locator(sel)
                            if loc.count() > 0:
                                loc.first.click()
                                clicked = True
                                if progress_cb:
                                    progress_cb(i, total, f"   submit via click {sel}")
                                break
                    if not clicked:
                        raise Exception("No se encontró botón de submit ni SubmitItem()")
                    if dialog_messages and progress_cb:
                        for dm in dialog_messages[:5]:
                            progress_cb(i, total, f"   JS: {dm}")

                    try:
                        page.wait_for_url(re.compile(r"filedetails|workshop"), timeout=60000)
                    except PWTimeout:
                        pass

                    final_url = page.url
                    m = re.search(r"[?&]id=(\d{6,})", final_url)
                    if m:
                        results.append((path, True, f"OK (id={m.group(1)}) url={final_url}"))
                        if progress_cb:
                            progress_cb(i, total,
                                        f"[OK] {path.name} (Parte {part_num}): id={m.group(1)}")
                        _frag_appended = True
                        break
                    else:
                        try:
                            LOGS_DIR.mkdir(exist_ok=True)
                            dump = LOGS_DIR / f"pw_fail_{int(time.time())}.html"
                            dump.write_text(_redact_sensitive(page.content()), encoding="utf-8", errors="ignore")
                            _rotate_logs()
                        except Exception:
                            dump = None
                        msg = f"No pubid. URL final: {final_url}"
                        if dump:
                            msg += f" (dump: {dump})"
                        if _try == _MAX_FRAG_TRIES:
                            results.append((path, False, msg))
                            if progress_cb:
                                progress_cb(i, total, f"[FAIL] {path.name}: {msg}")
                            _frag_appended = True
                        else:
                            if progress_cb:
                                progress_cb(i, total,
                                            f"[RETRY {_try}/{_MAX_FRAG_TRIES}] {path.name}: {msg}")

                except Exception as e:
                    _is_session = ("login" in str(e).lower()
                                   or "cookies inválidas" in str(e).lower()
                                   or "sesión expirada" in str(e).lower())
                    if _is_session or _try == _MAX_FRAG_TRIES:
                        results.append((path, False, f"Excepción: {e}"))
                        if progress_cb:
                            progress_cb(i, total, f"[ERR] {path.name}: {e}")
                        _frag_appended = True
                        break
                    if progress_cb:
                        progress_cb(i, total,
                                    f"[RETRY {_try}/{_MAX_FRAG_TRIES}] {path.name}: {e}")

            if not _frag_appended:
                results.append((path, False, "Error desconocido tras todos los intentos"))

            if i < total:
                time.sleep(UPLOAD_DELAY_SEC)

        browser.close()

    return results

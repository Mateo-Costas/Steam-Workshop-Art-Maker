#!/usr/bin/env python3
"""
WorkshopArt - main entry point.

Bootstraps the application: forces UTF-8 I/O, creates the SteamWorkshopAppData
tree, downloads missing tools on first run (FFmpeg, Real-ESRGAN, RIFE, gifski)
behind a splash screen, then launches the main window. ``--upload-tool`` opens
the Steam upload tool instead (used by the compiled .exe).
"""

import io
import queue
import sys
import tarfile
import threading
import time
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

import app_paths  # noqa: E402  (needs the src/ path above)
from app_paths import APP_VERSION, DATA_DIR, LOGS_DIR, RIFE_DIR, make_temp_dir  # noqa: E402

_LOG_MAX_BYTES = 5 * 1024 * 1024


def _setup_logging() -> None:
    """Create the runtime folders and make stdout/stderr safe for UTF-8 text.

    Windowed PyInstaller builds have no console (stdout/stderr are None), so
    both are redirected to SteamWorkshopAppData/logs/runtime.log, which is
    reset when it grows beyond 5 MB.
    """
    app_paths.ensure_dirs()
    log_file = LOGS_DIR / "runtime.log"
    try:
        if log_file.exists() and log_file.stat().st_size > _LOG_MAX_BYTES:
            log_file.replace(log_file.with_suffix(".old.log"))
        log_stream = open(log_file, "a", encoding="utf-8", buffering=1)
    except OSError:
        log_stream = io.StringIO()
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name)
        if stream is None:
            setattr(sys, name, log_stream)
        elif (getattr(stream, "encoding", "") or "").lower().replace("-", "") != "utf8":
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (AttributeError, ValueError):
                setattr(sys, name, io.TextIOWrapper(stream.buffer, encoding="utf-8",
                                                    errors="replace"))


_setup_logging()

import tkinter as tk  # noqa: E402
from tkinter import messagebox, ttk  # noqa: E402

from app_paths import find_tool  # noqa: E402
from downloads import download_file  # noqa: E402

FFMPEG_URL = ("https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/"
              "ffmpeg-master-latest-win64-gpl.zip")
RIFE_URL = ("https://github.com/nihui/rife-ncnn-vulkan/releases/download/20221029/"
            "rife-ncnn-vulkan-20221029-windows.zip")
GIFSKI_API = "https://api.github.com/repos/ImageOptim/gifski/releases/latest"
GIFSKI_FALLBACK_URL = ("https://github.com/ImageOptim/gifski/releases/download/1.34.0/"
                       "gifski-1.34.0.tar.xz")


# ---------------------------------------------------------------------------
# Tool installers (run in a worker thread; ``log`` reports to the splash)
# ---------------------------------------------------------------------------

def _extract_member(archive: Path, wanted: str, dest: Path) -> bool:
    """Copy the first archive member whose file name is ``wanted`` to ``dest``."""
    if archive.name.endswith((".tar.xz", ".tar.gz", ".tgz")):
        with tarfile.open(archive) as tf:
            for member in tf.getmembers():
                if member.isfile() and Path(member.name).name.lower() == wanted:
                    dest.write_bytes(tf.extractfile(member).read())
                    return True
        return False
    with zipfile.ZipFile(archive) as zf:
        for name in zf.namelist():
            if Path(name).name.lower() == wanted:
                dest.write_bytes(zf.read(name))
                return True
    return False


def install_ffmpeg(work: Path, log) -> None:
    archive = download_file(FFMPEG_URL, work / "ffmpeg.zip", "FFmpeg", log)
    if not _extract_member(archive, "ffmpeg.exe", DATA_DIR / "ffmpeg.exe"):
        raise RuntimeError("ffmpeg.exe no esta en el archivo descargado")


def install_gifski(work: Path, log) -> None:
    """gifski publishes a .tar.xz with binaries for every OS (win/gifski.exe)."""
    import requests
    url = GIFSKI_FALLBACK_URL
    try:
        release = requests.get(GIFSKI_API, timeout=15,
                               headers={"Accept": "application/vnd.github+json"}).json()
        for asset in release.get("assets", []):
            if asset["name"].endswith((".tar.xz", ".zip")) and "deb" not in asset["name"]:
                url = asset["browser_download_url"]
                break
    except (requests.RequestException, ValueError, KeyError) as e:
        log(f"GitHub API no disponible ({e}), usando gifski 1.34.0", None)
    archive = download_file(url, work / Path(url).name, "gifski", log)
    if not _extract_member(archive, "gifski.exe", DATA_DIR / "gifski.exe"):
        raise RuntimeError("gifski.exe no esta en el archivo descargado")


def install_rife(work: Path, log) -> None:
    archive = download_file(RIFE_URL, work / "rife.zip", "RIFE", log)
    with zipfile.ZipFile(archive) as zf:
        for member in zf.infolist():
            parts = Path(member.filename).parts
            if member.is_dir() or len(parts) < 2:
                continue
            name = parts[-1]
            if name.lower().endswith((".exe", ".dll")):
                dest = DATA_DIR / name
            elif parts[-2].startswith("rife") and name.endswith((".bin", ".param")):
                dest = RIFE_DIR / parts[-2] / name
            else:
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(zf.read(member))


def _rife_models_present() -> bool:
    return any(RIFE_DIR.glob("rife-*/*.bin")) or any(app_paths.APP_DIR.glob("rife-*/*.bin"))


def check_dependencies(log) -> bool:
    """Verify every tool, downloading what is missing. False if FFmpeg is unavailable."""
    from config import Config
    from models import ModelManager

    work = make_temp_dir("wkart_setup_")
    try:
        if find_tool("ffmpeg"):
            log("FFmpeg disponible", None)
        else:
            log("Descargando FFmpeg (necesario)...", 0)
            try:
                install_ffmpeg(work, log)
            except Exception as e:
                log(f"ERROR: no se pudo descargar FFmpeg: {e}", None)
                return False

        config = Config()
        manager = ModelManager(app_paths.resolve(config.get("paths.models")))
        if manager.check_executable() and len(manager.check_available_models()) >= 3:
            log("Modelos de IA disponibles", None)
        else:
            log("Descargando modelos de IA (Real-ESRGAN / Real-CUGAN)...", 0)
            if not manager.download_all_models(log):
                log("Modelos de IA no disponibles: puedes descargarlos luego desde el paso 2", None)

        optional = (
            ("RIFE", lambda: find_tool("rife-ncnn-vulkan") and _rife_models_present(), install_rife),
            ("gifski", lambda: find_tool("gifski"), install_gifski),
        )
        for label, present, installer in optional:
            if present():
                log(f"{label} disponible", None)
                continue
            log(f"Descargando {label}...", 0)
            try:
                installer(work, log)
            except Exception as e:  # optional tools: the app works without them
                log(f"{label} no disponible ({e})", None)
        return True
    finally:
        import shutil
        shutil.rmtree(work, ignore_errors=True)


# ---------------------------------------------------------------------------
# Splash screen
# ---------------------------------------------------------------------------

def run_splash() -> bool:
    """Show the startup splash while check_dependencies runs in a worker thread."""
    splash = tk.Tk()
    splash.title(f"WorkshopArt v{APP_VERSION}")
    splash.configure(bg="#0d1117")
    splash.resizable(False, False)
    width, height = 600, 400
    x = (splash.winfo_screenwidth() - width) // 2
    y = (splash.winfo_screenheight() - height) // 2
    splash.geometry(f"{width}x{height}+{x}+{y}")

    tk.Label(splash, text=f"WorkshopArt v{APP_VERSION}", font=("Segoe UI", 24, "bold"),
             bg="#0d1117", fg="#58a6ff").pack(pady=(20, 6))
    status = tk.Label(splash, text="Comprobando herramientas...", font=("Segoe UI", 13),
                      bg="#0d1117", fg="#f0f6fc")
    status.pack(pady=6)
    progress = ttk.Progressbar(splash, length=500, mode="indeterminate")
    progress.pack(pady=12)
    progress.start()
    log_box = tk.Text(splash, height=12, width=70, bg="#21262d", fg="#adbac7",
                      font=("Consolas", 9), wrap=tk.WORD, relief="flat")
    log_box.pack(padx=20, pady=(4, 20), fill="both", expand=True)

    messages: "queue.Queue[tuple]" = queue.Queue()
    outcome = {"ok": False, "done": False, "downloaded": False}

    def log(message, percent=None):
        messages.put((message, percent))
        if percent is not None:
            outcome["downloaded"] = True

    def worker():
        try:
            outcome["ok"] = check_dependencies(log)
        except Exception as e:
            log(f"ERROR inesperado: {e}", None)
        finally:
            outcome["done"] = True

    def pump():
        while not messages.empty():
            message, percent = messages.get_nowait()
            log_box.insert(tk.END, f"[{time.strftime('%H:%M:%S')}] {message}\n")
            log_box.see(tk.END)
            if percent is not None:
                status.config(text=message)
        if not outcome["done"]:
            splash.after(100, pump)
            return
        progress.stop()
        if outcome["ok"]:
            status.config(text="Listo. Abriendo WorkshopArt...")
            splash.after(1500 if outcome["downloaded"] else 300, splash.destroy)
        else:
            messagebox.showerror(
                "Error de inicializacion",
                "No se pudo preparar FFmpeg, que es imprescindible.\n\n"
                "Posibles causas:\n- Sin conexion a internet\n"
                "- Firewall o antivirus bloqueando la descarga\n- Disco lleno\n\n"
                f"Detalles en {LOGS_DIR / 'runtime.log'}", parent=splash)
            splash.destroy()

    threading.Thread(target=worker, daemon=True).start()
    splash.after(100, pump)
    splash.mainloop()
    return outcome["ok"]


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------

def run_upload_tool() -> int:
    """Open the Steam upload tool (``--upload-tool [--fragments ...] [--preset key]``)."""
    try:
        from upload_tool import UploadApp, parse_cli_args
        files, preset = parse_cli_args(sys.argv[1:])
        UploadApp(preloaded_files=files, preset_key=preset).mainloop()
        return 0
    except Exception as e:
        import traceback
        messagebox.showerror("Upload Tool", f"{e}\n\n{traceback.format_exc()}")
        return 1


def main() -> int:
    """Run the dependency checks, then the main window."""
    try:
        if not run_splash():
            return 1
        from ui.app import WorkshopArtGUI
        WorkshopArtGUI().run()
        return 0
    except Exception as e:
        import traceback
        traceback.print_exc()
        try:
            messagebox.showerror("Error critico", f"{e}\n\n{traceback.format_exc()}")
        except tk.TclError:
            pass
        return 1


if __name__ == "__main__":
    sys.exit(run_upload_tool() if "--upload-tool" in sys.argv else main())

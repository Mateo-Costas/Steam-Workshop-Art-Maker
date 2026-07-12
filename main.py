#!/usr/bin/env python3
"""
WorkshopArt v1.0 - Main entry point.

Bootstraps the application: sets up UTF-8 I/O, creates the
SteamWorkshopAppData directory tree, downloads missing binaries
(FFmpeg, Real-ESRGAN, gifski, RIFE) on first run, then launches
the main GUI. Also handles the --upload-tool CLI flag for the
PRO upload flow.
"""

import sys
import os
import io
from pathlib import Path

# ---------------------------------------------------------------------------
# Forzar UTF-8 en stdout/stderr ANTES de cualquier print/log.
# En modo windowed (frozen console=False) stdout/stderr son None.
# En modo terminal pueden tener encoding cp1252 (Windows).
# ---------------------------------------------------------------------------
# Resolve app root: sys.executable parent when frozen (PyInstaller), otherwise the script directory.
_APP_DIR = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).parent
_APP_DATA = _APP_DIR / "SteamWorkshopAppData"   # all runtime data lives here (logs, models, temp)

def _setup_logging():
    """Create the runtime directory tree and force stdout/stderr to UTF-8.

    In windowed PyInstaller builds stdout/stderr are None; we redirect them to
    the log file so print() and logging still work without crashing.
    In console builds with non-UTF-8 encodings (e.g. cp1252 on Windows) we
    reconfigure the streams to UTF-8 so emojis in log messages don't raise errors.
    """
    _APP_DATA.mkdir(parents=True, exist_ok=True)
    (_APP_DATA / "logs").mkdir(parents=True, exist_ok=True)
    (_APP_DATA / "temp").mkdir(parents=True, exist_ok=True)
    (_APP_DATA / "models").mkdir(parents=True, exist_ok=True)
    (_APP_DATA / "rife").mkdir(parents=True, exist_ok=True)

    log_file = _APP_DATA / "logs" / "runtime.log"
    try:
        _lf = open(log_file, "a", encoding="utf-8", buffering=1)
        if sys.stdout is None:
            sys.stdout = _lf
        elif not hasattr(sys.stdout, 'encoding') or (sys.stdout.encoding or '').lower().replace('-', '') != 'utf8':
            try:
                sys.stdout.reconfigure(encoding='utf-8', errors='replace')
            except Exception:
                sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        if sys.stderr is None:
            sys.stderr = _lf
        elif not hasattr(sys.stderr, 'encoding') or (sys.stderr.encoding or '').lower().replace('-', '') != 'utf8':
            try:
                sys.stderr.reconfigure(encoding='utf-8', errors='replace')
            except Exception:
                sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    except Exception:
        if sys.stdout is None:
            sys.stdout = io.StringIO()
        if sys.stderr is None:
            sys.stderr = io.StringIO()

_setup_logging()

# Agregar src/ al path ANTES de importar módulos del proyecto
_project_root = Path(__file__).parent
sys.path.insert(0, str(_project_root / "src"))
sys.path.insert(0, str(_project_root))

from tkinter import messagebox
import tkinter as tk
from tkinter import ttk
import threading
import time
import subprocess as _sp
import platform as _pf

_NO_WINDOW_FLAGS = {'creationflags': _sp.CREATE_NO_WINDOW} if _pf.system() == 'Windows' else {}

from ui.app import WorkshopArtGUI


# ---------------------------------------------------------------------------
# Helpers de ruta — siempre absolutas
# ---------------------------------------------------------------------------

def _bin(name: str) -> Path:
    """Return the absolute path for a binary inside SteamWorkshopAppData/."""
    return _APP_DATA / name


def _safe_log(log_widget, message: str):
    """Append a timestamped line to the splash Text widget, swallowing any exceptions."""
    timestamp = time.strftime("%H:%M:%S")
    try:
        log_widget.insert(tk.END, f"[{timestamp}] {message}\n")
        log_widget.see(tk.END)
        log_widget.update()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Splash screen
# ---------------------------------------------------------------------------

def show_download_splash():
    splash = tk.Tk()
    splash.title("WorkshopArt v1.0")
    splash.geometry("600x400")
    splash.configure(bg="#0d1117")
    splash.resizable(False, False)

    splash.update_idletasks()
    x = (splash.winfo_screenwidth() // 2) - 300
    y = (splash.winfo_screenheight() // 2) - 200
    splash.geometry(f"600x400+{x}+{y}")

    tk.Label(splash, text="WorkshopArt v1.0",
             font=('Segoe UI', 24, 'bold'), bg="#0d1117", fg="#58a6ff").pack(pady=20)

    subtitle = tk.Label(splash, text="Inicializando sistema...",
                        font=('Segoe UI', 14), bg="#0d1117", fg="#f0f6fc")
    subtitle.pack(pady=10)

    progress_frame = tk.Frame(splash, bg="#0d1117")
    progress_frame.pack(pady=20)
    progress = ttk.Progressbar(progress_frame, length=500, mode='indeterminate')
    progress.pack()
    progress.start()

    log_frame = tk.Frame(splash, bg="#0d1117")
    log_frame.pack(pady=20, padx=20, fill="both", expand=True)

    log_text = tk.Text(log_frame, height=12, width=70,
                       bg="#21262d", fg="#8b949e",
                       font=('Consolas', 9), wrap=tk.WORD)
    log_text.pack(side="left", fill="both", expand=True)

    scrollbar = tk.Scrollbar(log_frame, command=log_text.yview)
    scrollbar.pack(side="right", fill="y")
    log_text.config(yscrollcommand=scrollbar.set)

    return splash, subtitle, log_text, progress


# ---------------------------------------------------------------------------
# Verificaciones de existencia — rutas absolutas
# ---------------------------------------------------------------------------

def check_ffmpeg_exists() -> bool:
    """Return True if a working FFmpeg binary is found (in SteamWorkshopAppData/, app dir, or PATH)."""
    for p in [_bin("ffmpeg.exe"), _APP_DIR / "ffmpeg.exe"]:
        try:
            if p.exists():
                r = _sp.run([str(p), "-version"], capture_output=True, timeout=5,
                            **_NO_WINDOW_FLAGS)
                if r.returncode == 0:
                    return True
        except Exception:
            pass
    try:
        r = _sp.run(["ffmpeg", "-version"], capture_output=True, timeout=5,
                    **_NO_WINDOW_FLAGS)
        return r.returncode == 0
    except Exception:
        return False


def check_gifski_exists() -> bool:
    """Return True if gifski.exe is found. gifski is optional; absence falls back to FFmpeg palette."""
    for p in [_bin("gifski.exe"), _APP_DIR / "gifski.exe"]:
        if p.exists():
            return True
    try:
        r = _sp.run(["gifski", "--version"], capture_output=True, timeout=5,
                    **_NO_WINDOW_FLAGS)
        return r.returncode == 0
    except Exception:
        return False


def check_rife_exists() -> bool:
    """Return True if rife-ncnn-vulkan.exe is found. RIFE is used by the PRO animation enhancer."""
    for p in [_bin("rife-ncnn-vulkan.exe"), _APP_DIR / "rife-ncnn-vulkan.exe"]:
        if p.exists():
            return True
    return False


# ---------------------------------------------------------------------------
# Descarga de dependencias
# ---------------------------------------------------------------------------

def download_ffmpeg_portable(log_widget, status_label):
    """Download the ffmpeg-master-latest-win64-gpl.zip from BtbN's GitHub releases,
    extract ffmpeg.exe into SteamWorkshopAppData/, and verify it runs successfully."""
    import requests, zipfile, shutil

    _safe_log(log_widget, "Conectando con servidor FFmpeg...")
    status_label.config(text="Descargando FFmpeg...")

    url = ("https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/"
           "ffmpeg-master-latest-win64-gpl.zip")

    _safe_log(log_widget, "Iniciando descarga de FFmpeg...")
    response = requests.get(url, stream=True, timeout=90)
    response.raise_for_status()

    total_size = int(response.headers.get('content-length', 0))
    downloaded = 0
    temp_zip = _APP_DATA / "temp" / "ffmpeg_temp.zip"

    _safe_log(log_widget, f"Descargando FFmpeg ({total_size/(1024*1024):.1f} MB)...")
    with open(temp_zip, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)
                downloaded += len(chunk)
                if total_size > 0 and downloaded % (1024 * 1024) == 0:
                    pct = (downloaded / total_size) * 100
                    _safe_log(log_widget, f"  Progreso: {pct:.1f}%")

    dest = _bin("ffmpeg.exe")
    _safe_log(log_widget, "Extrayendo FFmpeg...")
    ffmpeg_found = False
    with zipfile.ZipFile(temp_zip, 'r') as zip_ref:
        for file_info in zip_ref.filelist:
            if file_info.filename.endswith("ffmpeg.exe"):
                with zip_ref.open(file_info) as source, open(dest, "wb") as target:
                    shutil.copyfileobj(source, target)
                ffmpeg_found = True
                _safe_log(log_widget, f"FFmpeg extraido en {dest}")
                break

    try:
        temp_zip.unlink()
    except Exception:
        pass

    if not ffmpeg_found:
        raise Exception("No se encontro ffmpeg.exe en el archivo descargado")

    if check_ffmpeg_exists():
        _safe_log(log_widget, "FFmpeg instalado y verificado")
    else:
        raise Exception("FFmpeg no funciona despues de la instalacion")


def download_ai_models(log_widget, status_label):
    """Download the Real-ESRGAN ncnn-vulkan release ZIP from GitHub and extract
    .bin/.param model files into SteamWorkshopAppData/models/ and the .exe into SteamWorkshopAppData/."""
    import requests, zipfile, shutil

    _safe_log(log_widget, "Conectando con GitHub para modelos IA...")
    status_label.config(text="Descargando modelos de IA...")

    url = ("https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/"
           "realesrgan-ncnn-vulkan-20220424-windows.zip")

    response = requests.get(url, stream=True, timeout=90)
    response.raise_for_status()

    total_size = int(response.headers.get('content-length', 0))
    downloaded = 0
    temp_zip = _APP_DATA / "temp" / "models_temp.zip"

    _safe_log(log_widget, f"Descargando modelos IA ({total_size/(1024*1024):.1f} MB)...")
    with open(temp_zip, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)
                downloaded += len(chunk)
                if total_size > 0 and downloaded % (2 * 1024 * 1024) == 0:
                    pct = (downloaded / total_size) * 100
                    _safe_log(log_widget, f"  {pct:.1f}%")

    extracted_models = 0
    extracted_exe = False
    _safe_log(log_widget, "Extrayendo modelos y ejecutable IA...")

    with zipfile.ZipFile(temp_zip, 'r') as zip_ref:
        for file_info in zip_ref.filelist:
            filename = Path(file_info.filename).name
            if filename.endswith(('.bin', '.param')):
                target_path = _APP_DATA / "models" / filename
                with zip_ref.open(file_info) as source, open(target_path, "wb") as target:
                    shutil.copyfileobj(source, target)
                if filename.endswith('.bin'):
                    extracted_models += 1
                    _safe_log(log_widget, f"  Modelo: {filename}")
            elif filename.endswith('.exe') and 'realesrgan' in filename.lower():
                dest = _bin("realesrgan-ncnn-vulkan.exe")
                with zip_ref.open(file_info) as source, open(dest, "wb") as target:
                    shutil.copyfileobj(source, target)
                extracted_exe = True
                _safe_log(log_widget, f"  Ejecutable IA extraido en {dest}")

    try:
        temp_zip.unlink()
    except Exception:
        pass

    _safe_log(log_widget, f"IA instalada: {extracted_models} modelos, exe={extracted_exe}")


def download_rife(log_widget, status_label):
    """Download RIFE ncnn-vulkan from GitHub. Failure is non-fatal; animation interpolation
    is silently disabled if RIFE isn't present (PRO feature only)."""
    import requests, zipfile, shutil

    _safe_log(log_widget, "Conectando con GitHub para RIFE...")
    status_label.config(text="Descargando RIFE...")

    url = ("https://github.com/nihui/rife-ncnn-vulkan/releases/download/"
           "20221029/rife-ncnn-vulkan-20221029-windows.zip")

    response = requests.get(url, stream=True, timeout=90)
    response.raise_for_status()
    total_size = int(response.headers.get('content-length', 0))
    downloaded = 0
    temp_zip = _APP_DATA / "temp" / "rife_temp.zip"

    _safe_log(log_widget, f"Descargando RIFE ({total_size/(1024*1024):.1f} MB)...")
    with open(temp_zip, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)
                downloaded += len(chunk)
                if total_size > 0 and downloaded % (2 * 1024 * 1024) == 0:
                    pct = (downloaded / total_size) * 100
                    _safe_log(log_widget, f"  {pct:.1f}%")

    extracted_exe = False
    extracted_models = 0
    with zipfile.ZipFile(temp_zip, 'r') as zip_ref:
        for info in zip_ref.filelist:
            filename = Path(info.filename).name
            if filename.lower() == "rife-ncnn-vulkan.exe" and not extracted_exe:
                dest = _bin("rife-ncnn-vulkan.exe")
                with zip_ref.open(info) as src, open(dest, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                extracted_exe = True
                _safe_log(log_widget, f"  RIFE extraido en {dest}")
            elif "/rife" in info.filename.replace("\\", "/") and \
                    filename.endswith((".bin", ".param")):
                rel = Path(*Path(info.filename).parts[1:])
                tgt = _APP_DATA / "rife" / rel
                tgt.parent.mkdir(parents=True, exist_ok=True)
                with zip_ref.open(info) as src, open(tgt, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                if filename.endswith(".bin"):
                    extracted_models += 1

    try:
        temp_zip.unlink()
    except Exception:
        pass

    if not extracted_exe:
        raise Exception("rife-ncnn-vulkan.exe no encontrado en el zip")

    _safe_log(log_widget, f"RIFE instalado (+{extracted_models} modelos)")


def download_gifski(log_widget, status_label):
    """Fetch the latest gifski release from GitHub API, fall back to a known-good URL if the
    API call fails. Extracts gifski.exe into SteamWorkshopAppData/."""
    import requests, zipfile, shutil

    status_label.config(text="Descargando gifski...")
    _safe_log(log_widget, "Descargando gifski (encoder GIF avanzado)...")

    download_url = None
    version_name = "?"

    try:
        api_resp = requests.get(
            "https://api.github.com/repos/ImageOptim/gifski/releases/latest",
            timeout=12,
            headers={"Accept": "application/vnd.github.v3+json"},
        )
        api_resp.raise_for_status()
        release_data = api_resp.json()
        version_name = release_data.get("tag_name", "?")
        for asset in release_data.get("assets", []):
            if "win" in asset["name"].lower() and asset["name"].endswith(".zip"):
                download_url = asset["browser_download_url"]
                break
        if not download_url:
            for asset in release_data.get("assets", []):
                if asset["name"].endswith(".zip"):
                    download_url = asset["browser_download_url"]
                    break
    except Exception as api_err:
        _safe_log(log_widget, f"  GitHub API: {api_err} - usando URL directa")

    if not download_url:
        version_name = "1.32.0"
        download_url = (
            f"https://github.com/ImageOptim/gifski/releases/download/"
            f"{version_name}/gifski-{version_name}.zip"
        )

    _safe_log(log_widget, f"Descargando gifski {version_name}...")
    resp = requests.get(download_url, stream=True, timeout=90)
    resp.raise_for_status()

    total_size = int(resp.headers.get("content-length", 0))
    downloaded = 0
    temp_zip = _APP_DATA / "temp" / "gifski_temp.zip"

    with open(temp_zip, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)
                downloaded += len(chunk)
                if total_size > 0 and downloaded % (512 * 1024) == 0:
                    pct = (downloaded / total_size) * 100
                    _safe_log(log_widget, f"  {pct:.0f}%")

    dest = _bin("gifski.exe")
    gifski_found = False
    with zipfile.ZipFile(temp_zip, "r") as zf:
        for info in zf.filelist:
            if Path(info.filename).name.lower() == "gifski.exe":
                with zf.open(info) as src, open(dest, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                gifski_found = True
                _safe_log(log_widget, f"gifski extraido en {dest}")
                break

    try:
        temp_zip.unlink()
    except Exception:
        pass

    if not gifski_found:
        raise Exception("gifski.exe no encontrado en el ZIP")

    _safe_log(log_widget, "gifski instalado")


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def create_default_config():
    """Write a starter config.json with all required path and quality defaults."""
    import json
    config = {
        "paths": {
            "ffmpeg": str(_bin("ffmpeg.exe")),
            "realesrgan": str(_APP_DATA),
            "models": str(_APP_DATA / "models"),
            "temp_dir": str(_APP_DATA / "temp"),
        },
        "steam_profile": {
            "width": 638, "height": 354, "parts": 5,
            "min_size_mb": 4.4, "max_size_mb": 4.8
        },
        "gpu": {"use_gpu": True, "gpu_id": 0},
        "quality": {"default_fps": 24, "max_fps": 60,
                    "contrast": 1.5, "saturation": 1.3}
    }
    cfg_path = _APP_DIR / "config.json"
    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4)


# ---------------------------------------------------------------------------
# Inicializacion de dependencias
# ---------------------------------------------------------------------------

def check_and_download_dependencies() -> bool:
    """Show the startup splash and verify/download all required binaries.

    Checks in order: FFmpeg, Real-ESRGAN models, RIFE, gifski, config.json.
    Each missing binary triggers an automatic download. Returns True on success,
    False if a critical dependency (FFmpeg) could not be installed.
    """
    splash, status_label, log_widget, progress = show_download_splash()
    downloaded_something = False

    try:
        _safe_log(log_widget, "WorkshopArt v1.0 - Inicializando...")
        _safe_log(log_widget, "Verificando sistema...")

        # Asegurar directorios
        for sub in ("models", "logs", "temp", "rife"):
            (_APP_DATA / sub).mkdir(parents=True, exist_ok=True)
        _safe_log(log_widget, f"Directorios OK en {_APP_DATA}")

        # FFmpeg
        status_label.config(text="Verificando FFmpeg...")
        if not check_ffmpeg_exists():
            _safe_log(log_widget, "FFmpeg no encontrado, descargando...")
            download_ffmpeg_portable(log_widget, status_label)
            downloaded_something = True
        else:
            _safe_log(log_widget, "FFmpeg disponible")

        # Modelos IA
        status_label.config(text="Verificando modelos de IA...")
        model_files = list((_APP_DATA / "models").glob("*.bin"))
        if len(model_files) < 3:
            _safe_log(log_widget, f"Solo {len(model_files)} modelos, descargando...")
            download_ai_models(log_widget, status_label)
            downloaded_something = True
        else:
            _safe_log(log_widget, f"{len(model_files)} modelos de IA disponibles")

        # RIFE
        status_label.config(text="Verificando RIFE...")
        if not check_rife_exists():
            _safe_log(log_widget, "RIFE no encontrado, descargando...")
            try:
                download_rife(log_widget, status_label)
                downloaded_something = True
            except Exception as e:
                _safe_log(log_widget, f"RIFE no disponible: {e} (interpolacion deshabilitada)")
        else:
            _safe_log(log_widget, "RIFE disponible")

        # gifski
        status_label.config(text="Verificando gifski...")
        if not check_gifski_exists():
            _safe_log(log_widget, "gifski no encontrado, descargando...")
            try:
                download_gifski(log_widget, status_label)
                downloaded_something = True
            except Exception as e:
                _safe_log(log_widget, f"gifski no disponible: {e} (fallback a ffmpeg)")
        else:
            _safe_log(log_widget, "gifski disponible")

        # Config
        cfg_path = _APP_DIR / "config.json"
        if not cfg_path.exists():
            create_default_config()
            _safe_log(log_widget, "Configuracion por defecto creada")
        else:
            _safe_log(log_widget, "Configuracion existente encontrada")

        progress.stop()
        progress.config(mode='determinate', value=100)
        _safe_log(log_widget, "")
        _safe_log(log_widget, "Sistema listo. Iniciando WorkshopArt...")
        status_label.config(text="Listo! Iniciando WorkshopArt v1.0...")

        # Fast path: nothing was downloaded, so don't hold the user 3 s staring
        # at the splash — close it almost immediately.
        splash.after(3000 if downloaded_something else 500, splash.destroy)
        splash.mainloop()
        return True

    except Exception as e:
        import traceback
        err = f"{e}\n\n{traceback.format_exc()}"
        _safe_log(log_widget, f"Error critico: {err}")
        progress.stop()
        messagebox.showerror("Error de Inicializacion",
                             f"Error configurando el sistema:\n\n{e}\n\n"
                             f"Posibles causas:\n"
                             f"- Sin conexion a internet\n"
                             f"- Firewall bloqueando descargas\n"
                             f"- Espacio insuficiente en disco")
        splash.destroy()
        return False


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run_upload_tool():
    """Entry point for --upload-tool CLI flag. Launches the PRO UploadApp as a subprocess.
    Accepts optional --fragments <paths> and --preset <key> arguments."""
    try:
        from upload_tool import UploadApp
        preload = []
        preset_key = None
        if '--fragments' in sys.argv:
            idx = sys.argv.index('--fragments')
            # Consume args only until the next flag; otherwise the value of
            # --preset would be swallowed as a bogus fragment path.
            for p in sys.argv[idx + 1:]:
                if p.startswith('--'):
                    break
                preload.append(Path(p))
        if '--preset' in sys.argv:
            idx = sys.argv.index('--preset')
            if idx + 1 < len(sys.argv):
                preset_key = sys.argv[idx + 1]
        app = UploadApp(preloaded_files=preload, preset_key=preset_key)
        app.mainloop()
    except Exception as e:
        import traceback
        try:
            messagebox.showerror("Upload Tool Error",
                                 f"{e}\n\n{traceback.format_exc()}")
        except Exception:
            pass


def main():
    """Application entry point: run dependency checks then start the GUI."""
    try:
        if not check_and_download_dependencies():
            return 1

        app = WorkshopArtGUI()
        app.run()
        return 0

    except Exception as e:
        import traceback
        error_msg = f"Error critico:\n\n{e}\n\n{traceback.format_exc()}"
        try:
            messagebox.showerror("Error Critico", error_msg)
        except Exception:
            pass
        return 1


if __name__ == "__main__":
    # --upload-tool flag is passed by the GUI sidebar button via subprocess.Popen
    if "--upload-tool" in sys.argv:
        sys.exit(run_upload_tool())
    else:
        sys.exit(main())

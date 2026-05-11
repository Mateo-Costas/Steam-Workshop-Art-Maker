#!/usr/bin/env python3
"""
WorkshopArt PRO v1.0 - Archivo Principal AUTOCONTENIDO
Punto de entrada con descarga automática de dependencias
"""

import sys
import os
from pathlib import Path

# Agregar src/ al path ANTES de importar módulos del proyecto
_project_root = Path(__file__).parent
sys.path.insert(0, str(_project_root / "src"))
sys.path.insert(0, str(_project_root))

# ---------------------------------------------------------------------------
# Modo windowed (PyInstaller --noconsole): sys.stdout/sys.stderr son None y
# cualquier print() o traceback revienta con AttributeError. Redirigimos a
# un archivo de log para no perder la traza y evitar crashes silenciosos.
# ---------------------------------------------------------------------------
_APP_DATA = (Path(sys.executable).parent if getattr(sys, 'frozen', False)
             else _project_root) / "SteamWorkshopAppData"

if sys.stdout is None or sys.stderr is None:
    _logs_root = _APP_DATA / "logs"
    try:
        _logs_root.mkdir(parents=True, exist_ok=True)
        _log_file = open(_logs_root / "runtime.log", "a", encoding="utf-8",
                         buffering=1)  # line-buffered
        sys.stdout = _log_file
        sys.stderr = _log_file
    except Exception:
        # Último recurso: sumidero silencioso
        import io as _io
        sys.stdout = _io.StringIO()
        sys.stderr = _io.StringIO()

from tkinter import messagebox
import tkinter as tk
from tkinter import ttk
import threading
import time

from gui import WorkshopArtGUI
from theme_PRO import ModernThemePro

def show_download_splash():
    """Mostrar splash screen durante descargas"""
    splash = tk.Tk()
    splash.title("🎮 WorkshopArt PRO v1.0")
    splash.geometry("600x400")
    splash.configure(bg="#0d1117")
    splash.resizable(False, False)
    
    # Centrar ventana
    splash.update_idletasks()
    x = (splash.winfo_screenwidth() // 2) - (300)
    y = (splash.winfo_screenheight() // 2) - (200)
    splash.geometry(f"600x400+{x}+{y}")
    
    # Contenido del splash
    title = tk.Label(splash, text="🎮 WorkshopArt PRO v1.0", 
                    font=('Segoe UI', 24, 'bold'),
                    bg="#0d1117", fg="#58a6ff")
    title.pack(pady=20)
    
    subtitle = tk.Label(splash, text="Inicializando sistema...", 
                       font=('Segoe UI', 14),
                       bg="#0d1117", fg="#f0f6fc")
    subtitle.pack(pady=10)
    
    # Barra de progreso
    progress_frame = tk.Frame(splash, bg="#0d1117")
    progress_frame.pack(pady=20)
    
    progress = ttk.Progressbar(progress_frame, length=500, mode='indeterminate')
    progress.pack()
    progress.start()
    
    # Log de estado con scroll
    log_frame = tk.Frame(splash, bg="#0d1117")
    log_frame.pack(pady=20, padx=20, fill="both", expand=True)
    
    log_text = tk.Text(log_frame, height=12, width=70,
                      bg="#21262d", fg="#8b949e",
                      font=('Consolas', 9),
                      wrap=tk.WORD)
    log_text.pack(side="left", fill="both", expand=True)
    
    scrollbar = tk.Scrollbar(log_frame, command=log_text.yview)
    scrollbar.pack(side="right", fill="y")
    log_text.config(yscrollcommand=scrollbar.set)
    
    return splash, subtitle, log_text, progress

def log_to_splash(log_widget, message):
    """Agregar mensaje al log del splash"""
    timestamp = time.strftime("%H:%M:%S")
    log_widget.insert(tk.END, f"[{timestamp}] {message}\n")
    log_widget.see(tk.END)
    log_widget.update()

def check_and_download_dependencies():
    """Verificar y descargar todas las dependencias automáticamente"""
    
    splash, status_label, log_widget, progress = show_download_splash()
    
    try:
        log_to_splash(log_widget, "🎮 WorkshopArt PRO v1.0 - Inicializando...")
        log_to_splash(log_widget, "🔍 Verificando sistema...")
        
        # Crear directorios necesarios dentro de SteamWorkshopAppData/
        for sub in ("models", "logs", "temp", "rife"):
            (_APP_DATA / sub).mkdir(parents=True, exist_ok=True)
        log_to_splash(log_widget, f"✅ Directorios creados en SteamWorkshopAppData/")
        
        # 1. Verificar/Descargar FFmpeg
        status_label.config(text="Verificando FFmpeg...")
        log_to_splash(log_widget, "🔍 Verificando FFmpeg...")
        
        if not check_ffmpeg_exists():
            log_to_splash(log_widget, "📥 FFmpeg no encontrado, descargando...")
            download_ffmpeg_portable(log_widget, status_label)
        else:
            log_to_splash(log_widget, "✅ FFmpeg ya disponible")
        
        # 2. Verificar/Descargar modelos IA
        status_label.config(text="Verificando modelos de IA...")
        log_to_splash(log_widget, "🔍 Verificando modelos de IA...")

        models_dir = _APP_DATA / "models"
        model_files = list(models_dir.glob("*.bin"))

        if len(model_files) < 3:  # Necesitamos al menos 3 modelos
            log_to_splash(log_widget, f"📥 Solo {len(model_files)} modelos encontrados, descargando completos...")
            download_ai_models(log_widget, status_label)
        else:
            log_to_splash(log_widget, f"✅ {len(model_files)} modelos de IA disponibles")

        # 2b. Verificar/Descargar RIFE (interpolación de frames a 60fps)
        status_label.config(text="Verificando RIFE...")
        log_to_splash(log_widget, "🔍 Verificando RIFE (interpolación 60fps)...")
        if not Path("rife-ncnn-vulkan.exe").exists():
            log_to_splash(log_widget, "📥 RIFE no encontrado, descargando...")
            try:
                download_rife(log_widget, status_label)
            except Exception as _rife_err:
                log_to_splash(log_widget,
                              f"⚠️ RIFE no se pudo descargar: {_rife_err}")
                log_to_splash(log_widget,
                              "   (La interpolación a 60fps estará deshabilitada)")
        else:
            log_to_splash(log_widget, "✅ RIFE disponible")

        # 2c. Verificar/Descargar gifski (encoder GIF de alta calidad)
        status_label.config(text="Verificando gifski...")
        log_to_splash(log_widget, "🔍 Verificando gifski (encoder GIF)...")
        if not check_gifski_exists():
            log_to_splash(log_widget, "📥 gifski no encontrado, descargando...")
            try:
                download_gifski(log_widget, status_label)
            except Exception as _gifski_err:
                log_to_splash(log_widget, f"⚠️ gifski no se pudo descargar: {_gifski_err}")
                log_to_splash(log_widget,
                              "   (Artwork Showcase usará ffmpeg como fallback)")
        else:
            log_to_splash(log_widget, "✅ gifski disponible")
        
        # 3. Verificar configuración
        if not Path("config.json").exists():
            create_default_config()
            log_to_splash(log_widget, "✅ Configuración por defecto creada")
        else:
            log_to_splash(log_widget, "✅ Configuración existente encontrada")
        
       
        
        # Finalización
        progress.stop()
        progress.config(mode='determinate', value=100)
        
        log_to_splash(log_widget, "")
        log_to_splash(log_widget, "🎉 ¡Sistema completamente configurado!")
        log_to_splash(log_widget, "✨ Iniciando WorkshopArt PRO...")
        status_label.config(text="¡Listo! Iniciando WorkshopArt PRO...")
        
        # Esperar un momento para que el usuario vea el mensaje
        splash.after(3000, splash.destroy)
        splash.mainloop()
        
        return True
        
    except Exception as e:
        log_to_splash(log_widget, f"❌ Error crítico: {e}")
        progress.stop()
        
        messagebox.showerror("Error de Inicialización", 
                           f"Error configurando el sistema:\n\n{e}\n\n"
                           f"La aplicación se cerrará.\n\n"
                           f"Posibles causas:\n"
                           f"• Sin conexión a internet\n"
                           f"• Firewall bloqueando descargas\n"
                           f"• Espacio insuficiente en disco")
        
        splash.destroy()
        return False

def check_ffmpeg_exists():
    """Verificar si FFmpeg está disponible"""
    try:
        import subprocess
        # Verificar en PATH del sistema
        result = subprocess.run(["ffmpeg", "-version"], 
                              capture_output=True, timeout=5)
        return result.returncode == 0
    except:
        try:
            # Verificar en directorio local
            local_ffmpeg = Path("ffmpeg.exe")
            if local_ffmpeg.exists():
                result = subprocess.run([str(local_ffmpeg), "-version"], 
                                      capture_output=True, timeout=5)
                return result.returncode == 0
        except:
            pass
        return False

def download_ffmpeg_portable(log_widget, status_label):
    """Descargar FFmpeg portable"""
    try:
        import requests
        import zipfile
        
        log_to_splash(log_widget, "🌐 Conectando con servidor FFmpeg...")
        status_label.config(text="Descargando FFmpeg...")
        
        # URL de FFmpeg portable (versión estática)
        url = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
        
        log_to_splash(log_widget, "📡 Iniciando descarga de FFmpeg...")
        
        # Descargar con progreso
        response = requests.get(url, stream=True, timeout=60)
        response.raise_for_status()
        
        total_size = int(response.headers.get('content-length', 0))
        downloaded = 0
        
        log_to_splash(log_widget, f"📦 Descargando FFmpeg ({total_size/(1024*1024):.1f} MB)...")
        
        with open(_APP_DATA / "temp" / "ffmpeg_temp.zip", "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size > 0:
                        progress = (downloaded / total_size) * 100
                        if downloaded % (1024*1024) == 0:  # Log cada MB
                            log_to_splash(log_widget, f"  📊 Progreso: {progress:.1f}% ({downloaded/(1024*1024):.1f} MB)")
        
        # Extraer solo el ejecutable
        log_to_splash(log_widget, "📂 Extrayendo FFmpeg...")
        
        ffmpeg_found = False
        with zipfile.ZipFile(_APP_DATA / "temp" / "ffmpeg_temp.zip", 'r') as zip_ref:
            for file_info in zip_ref.filelist:
                # Buscar el ejecutable FFmpeg en cualquier subdirectorio
                if file_info.filename.endswith("ffmpeg.exe"):
                    log_to_splash(log_widget, f"  📋 Encontrado: {file_info.filename}")
                    
                    # Extraer solo el ejecutable
                    with zip_ref.open(file_info) as source, open("ffmpeg.exe", "wb") as target:
                        import shutil
                        shutil.copyfileobj(source, target)
                    
                    log_to_splash(log_widget, "✅ FFmpeg extraído correctamente")
                    ffmpeg_found = True
                    break
        
        # Verificar si se encontró FFmpeg
        if not ffmpeg_found:
            raise Exception("No se encontró ffmpeg.exe en el archivo descargado")
        
        # Limpiar archivo temporal
        os.remove(_APP_DATA / "temp" / "ffmpeg_temp.zip")
        log_to_splash(log_widget, "🧹 Archivos temporales limpiados")
        
        # Verificar que funciona
        if check_ffmpeg_exists():
            log_to_splash(log_widget, "✅ FFmpeg instalado y verificado correctamente")
        else:
            raise Exception("FFmpeg no funciona después de la instalación")
        
    except Exception as e:
        log_to_splash(log_widget, f"❌ Error descargando FFmpeg: {e}")
        raise

def download_ai_models(log_widget, status_label):
    """Descargar modelos de IA automáticamente"""
    try:
        import requests
        import zipfile
        import shutil
        
        log_to_splash(log_widget, "🌐 Conectando con GitHub para modelos IA...")
        status_label.config(text="Descargando modelos de IA...")
        
        # URL del paquete completo de Real-ESRGAN
        url = "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesrgan-ncnn-vulkan-20220424-windows.zip"
        
        log_to_splash(log_widget, "📡 Iniciando descarga de modelos IA...")
        
        # Descargar con progreso
        response = requests.get(url, stream=True, timeout=90)
        response.raise_for_status()
        
        total_size = int(response.headers.get('content-length', 0))
        downloaded = 0
        
        log_to_splash(log_widget, f"📦 Descargando modelos IA ({total_size/(1024*1024):.1f} MB)...")
        
        with open(_APP_DATA / "temp" / "models_temp.zip", "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size > 0:
                        progress = (downloaded / total_size) * 100
                        if downloaded % (2*1024*1024) == 0:  # Log cada 2MB
                            log_to_splash(log_widget, f"  📊 Progreso: {progress:.1f}% ({downloaded/(1024*1024):.1f} MB)")
        
        # Extraer modelos y ejecutable
        log_to_splash(log_widget, "📂 Extrayendo modelos y ejecutable IA...")
        
        extracted_models = 0
        extracted_exe = False
        
        with zipfile.ZipFile(_APP_DATA / "temp" / "models_temp.zip", 'r') as zip_ref:
            for file_info in zip_ref.filelist:
                filename = Path(file_info.filename).name
                
                # Extraer archivos de modelos (.bin y .param)
                if filename.endswith(('.bin', '.param')):
                    target_path = _APP_DATA / "models" / filename
                    
                    with zip_ref.open(file_info) as source, open(target_path, "wb") as target:
                        shutil.copyfileobj(source, target)
                    
                    if filename.endswith('.bin'):
                        extracted_models += 1
                        log_to_splash(log_widget, f"  📋 Modelo extraído: {filename}")
                
                # Extraer ejecutable Real-ESRGAN
                elif filename.endswith('.exe') and 'realesrgan' in filename.lower():
                    exe_name = "realesrgan-ncnn-vulkan.exe"
                    
                    with zip_ref.open(file_info) as source, open(exe_name, "wb") as target:
                        shutil.copyfileobj(source, target)
                    
                    extracted_exe = True
                    log_to_splash(log_widget, f"  🤖 Ejecutable IA extraído: {exe_name}")
        
        # Limpiar archivo temporal
        os.remove(_APP_DATA / "temp" / "models_temp.zip")
        log_to_splash(log_widget, "🧹 Archivos temporales limpiados")
        
        # Verificar extracción
        if extracted_models >= 3 and extracted_exe:
            log_to_splash(log_widget, f"✅ Sistema IA instalado: {extracted_models} modelos + ejecutable")
        else:
            log_to_splash(log_widget, f"⚠️ Extracción parcial: {extracted_models} modelos, exe: {extracted_exe}")
        
    except Exception as e:
        log_to_splash(log_widget, f"❌ Error descargando modelos IA: {e}")
        raise

def download_rife(log_widget, status_label):
    """Descargar rife-ncnn-vulkan (interpolación de frames)."""
    import requests
    import zipfile
    import shutil

    log_to_splash(log_widget, "🌐 Conectando con GitHub para RIFE...")
    status_label.config(text="Descargando RIFE...")

    # Build oficial Windows
    url = ("https://github.com/nihui/rife-ncnn-vulkan/releases/download/"
           "20221029/rife-ncnn-vulkan-20221029-windows.zip")

    response = requests.get(url, stream=True, timeout=90)
    response.raise_for_status()
    total_size = int(response.headers.get('content-length', 0))
    downloaded = 0
    log_to_splash(log_widget,
                  f"📦 Descargando RIFE ({total_size/(1024*1024):.1f} MB)...")

    with open(_APP_DATA / "temp" / "rife_temp.zip", "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)
                downloaded += len(chunk)
                if total_size > 0 and downloaded % (2 * 1024 * 1024) == 0:
                    pct = (downloaded / total_size) * 100
                    log_to_splash(log_widget,
                                  f"  📊 {pct:.1f}% ({downloaded/(1024*1024):.1f} MB)")

    log_to_splash(log_widget, "📂 Extrayendo RIFE + modelos...")
    extracted_exe = False
    extracted_models = 0
    with zipfile.ZipFile(_APP_DATA / "temp" / "rife_temp.zip", 'r') as zip_ref:
        for info in zip_ref.filelist:
            filename = Path(info.filename).name
            # exe
            if filename.lower() == "rife-ncnn-vulkan.exe" and not extracted_exe:
                with zip_ref.open(info) as src, open("rife-ncnn-vulkan.exe", "wb") as dst:
                    shutil.copyfileobj(src, dst)
                extracted_exe = True
                log_to_splash(log_widget, "  🤖 Ejecutable RIFE extraído")
            # modelos (carpetas rife-*, contienen .bin/.param)
            elif "/rife" in info.filename.replace("\\", "/") and \
                    filename.endswith((".bin", ".param")):
                # Preservar estructura dentro de SteamWorkshopAppData/rife/
                rel = Path(*Path(info.filename).parts[1:])  # strip top folder
                tgt = _APP_DATA / "rife" / rel
                tgt.parent.mkdir(parents=True, exist_ok=True)
                with zip_ref.open(info) as src, open(tgt, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                if filename.endswith(".bin"):
                    extracted_models += 1

    try:
        os.remove(_APP_DATA / "temp" / "rife_temp.zip")
    except Exception:
        pass

    if extracted_exe:
        log_to_splash(log_widget,
                      f"✅ RIFE instalado (+{extracted_models} modelos)")
    else:
        raise Exception("rife-ncnn-vulkan.exe no encontrado en el zip")


def check_gifski_exists():
    """Verificar si gifski está disponible"""
    try:
        import subprocess
        r = subprocess.run(["gifski", "--version"], capture_output=True, timeout=5)
        if r.returncode == 0:
            return True
    except Exception:
        pass
    return Path("gifski.exe").exists()


def download_gifski(log_widget, status_label):
    """Descargar gifski desde GitHub releases (encoder GIF de alta calidad)"""
    import requests
    import zipfile
    import shutil

    status_label.config(text="Descargando gifski...")
    log_to_splash(log_widget, "🎞️  gifski — encoder GIF con compresión perceptual avanzada")

    download_url = None
    version_name = "?"

    # Intentar obtener la última versión por la API de GitHub
    try:
        api_resp = requests.get(
            "https://api.github.com/repos/ImageOptim/gifski/releases/latest",
            timeout=12,
            headers={"Accept": "application/vnd.github.v3+json"},
        )
        api_resp.raise_for_status()
        release_data = api_resp.json()
        version_name = release_data.get("tag_name", "?")
        assets = release_data.get("assets", [])

        # Buscar ZIP de Windows (nombre con "win" primero, cualquier zip como fallback)
        for asset in assets:
            if "win" in asset["name"].lower() and asset["name"].endswith(".zip"):
                download_url = asset["browser_download_url"]
                break
        if not download_url:
            for asset in assets:
                if asset["name"].endswith(".zip"):
                    download_url = asset["browser_download_url"]
                    break
    except Exception as api_err:
        log_to_splash(log_widget, f"   API GitHub: {api_err} — usando URL directa")

    # Fallback a versión conocida
    if not download_url:
        version_name = "1.32.0"
        download_url = (
            "https://github.com/ImageOptim/gifski/releases/download/"
            f"{version_name}/gifski-{version_name}.zip"
        )

    log_to_splash(log_widget, f"📡 Descargando gifski {version_name}...")
    resp = requests.get(download_url, stream=True, timeout=90)
    resp.raise_for_status()

    total_size = int(resp.headers.get("content-length", 0))
    downloaded = 0
    temp_zip = _APP_DATA / "temp" / "gifski_temp.zip"

    log_to_splash(log_widget,
                  f"📦 Descargando ({total_size / (1024*1024):.1f} MB)..." if total_size else "📦 Descargando...")
    with open(temp_zip, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)
                downloaded += len(chunk)
                if total_size > 0 and downloaded % (512 * 1024) == 0:
                    pct = (downloaded / total_size) * 100
                    log_to_splash(log_widget, f"  📊 {pct:.0f}%")

    log_to_splash(log_widget, "📂 Extrayendo gifski.exe...")
    gifski_found = False
    with zipfile.ZipFile(temp_zip, "r") as zf:
        for info in zf.filelist:
            if Path(info.filename).name.lower() == "gifski.exe":
                with zf.open(info) as src, open("gifski.exe", "wb") as dst:
                    shutil.copyfileobj(src, dst)
                gifski_found = True
                log_to_splash(log_widget, "✅ gifski.exe extraído")
                break

    try:
        os.remove(temp_zip)
    except Exception:
        pass

    if not gifski_found:
        raise Exception("gifski.exe no encontrado dentro del ZIP descargado")

    log_to_splash(log_widget, "✅ gifski instalado — compresión GIF avanzada activa para Artwork Showcase")


def create_default_config():
    """Crear configuración por defecto"""
    import json
    
    config = {
        "paths": {
            "ffmpeg": "ffmpeg.exe",
            "realesrgan": ".",
            "models": "SteamWorkshopAppData/models",
            "temp_dir": "SteamWorkshopAppData/temp"
        },
        "steam_profile": {
            "width": 638,
            "height": 354,
            "parts": 5,
            "min_size_mb": 4.4,
            "max_size_mb": 4.8
        },
        "gpu": {
            "use_gpu": True,
            "gpu_id": 0
        },
        "quality": {
            "default_fps": 24,
            "max_fps": 60,
            "contrast": 1.5,
            "saturation": 1.3
        }
    }
    
    with open("config.json", "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4)

def check_dependencies():
    """Verificar que todas las dependencias estén instaladas"""
    missing_deps = []
    
    # Verificar dependencias críticas
    dependencies = [
        ("PIL", "pillow"),
        ("moviepy.editor", "moviepy"),
        ("cv2", "opencv-python"),
        ("numpy", "numpy"),
        ("matplotlib", "matplotlib"),
        ("requests", "requests"),
        ("tqdm", "tqdm")
    ]
    
    for import_name, package_name in dependencies:
        try:
            __import__(import_name)
        except ImportError:
            missing_deps.append(package_name)
    
    # Error solo si faltan dependencias críticas
    if missing_deps:
        error_msg = f"""❌ DEPENDENCIAS FALTANTES:

{', '.join(missing_deps)}

Este ejecutable no está completo.
Faltan librerías de Python integradas.

Soluciones:
1. Recompilar el .exe incluyendo todas las dependencias
2. Instalar manualmente: pip install {' '.join(missing_deps)}"""
        
        try:
            messagebox.showerror("Ejecutable Incompleto", error_msg)
        except:
            print(f"ERROR: {error_msg}")
        return False
    
    return True

def main():
    """Función principal SIMPLIFICADA"""
    try:
        print("🎮 WorkshopArt PRO v1.0 - Iniciando...")
        
        # Solo verificar y descargar dependencias externas
        if not check_and_download_dependencies():
            return 1
        
        print("✅ Todos los módulos cargados")
        print("🚀 Lanzando interfaz gráfica...")
        
        # Crear y ejecutar aplicación (ya importadas al inicio)
        app = WorkshopArtGUI()
        app.run()
        
        return 0
       
        
    except Exception as e:
        import traceback
        error_msg = f"Error critico:\n\n{e}\n\n{traceback.format_exc()}"
        print(error_msg)

        try:
            messagebox.showerror("Error Critico", error_msg)
        except:
            pass

        # En modo windowed no hay stdin; si existe, hace pausa.
        try:
            if sys.stdin and sys.stdin.isatty():
                input("\nPresiona ENTER para cerrar...")
        except Exception:
            pass
        return 1

def run_upload_tool():
    """Lanzar Upload Tool como ventana independiente (invocado con --upload-tool)."""
    try:
        from upload_tool import UploadApp
        app = UploadApp()
        app.mainloop()
    except Exception as e:
        import traceback
        try:
            messagebox.showerror("Upload Tool Error", f"{e}\n\n{traceback.format_exc()}")
        except Exception:
            print(f"Upload Tool Error: {e}")


if __name__ == "__main__":
    if "--upload-tool" in sys.argv:
        sys.exit(run_upload_tool())
    else:
        try:
            sys.exit(main())
        except Exception as e:
            import traceback
            print(f"\n{'='*60}")
            print(f"ERROR CRITICO: {e}")
            print(f"{'='*60}")
            traceback.print_exc()
            try:
                if sys.stdin and sys.stdin.isatty():
                    input("\nPresiona ENTER para cerrar...")
            except Exception:
                pass
            sys.exit(1)
"""Real UI check: opens the WorkshopArt window and uses it like a person would.

    python tests/ui_check.py

Loads files, walks the four steps, adjusts colors, converts a video,
fragments with several presets (checking the copied console snippet), opens
the preview, help and language switch, runs AI + RIFE (when installed), the
1-click pipeline, the size optimizer, the ZIP export and a cancellation.

Dialogs are answered automatically and recorded; a temporary config.json is
used. Any Tk callback exception, UI-queue error or error dialog is a failure.
Needs a display, the FFmpeg the app downloads and (for the AI part) the models.
"""
import sys
import tempfile
import time
import traceback
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import config as config_module  # noqa: E402
from app_paths import find_tool  # noqa: E402
from media import make_media  # noqa: E402

WORK = Path(tempfile.mkdtemp(prefix="wkart_uicheck_"))
config_module.CONFIG_FILE = WORK / "config.json"  # never touch the real config

from tkinter import filedialog, messagebox, simpledialog  # noqa: E402

dialogs = []
answers = {"file": "", "files": [], "float": 5.0}


def _record(kind):
    def show(title=None, message=None, **_kwargs):
        dialogs.append((kind, str(title), str(message)))
        return True
    return show


messagebox.showinfo = _record("info")
messagebox.showwarning = _record("warning")
messagebox.showerror = _record("error")
messagebox.askyesno = _record("ask")
filedialog.askopenfilename = lambda **_kw: str(answers["file"])
filedialog.askopenfilenames = lambda **_kw: tuple(str(p) for p in answers["files"])

import ui.logic.fragmentation as fragmentation  # noqa: E402
fragmentation.askfloat = lambda *_a, **_kw: answers["float"]
simpledialog.askfloat = fragmentation.askfloat

from ui.app import WorkshopArtGUI  # noqa: E402

failures, passed, tk_errors = [], 0, []
MEDIA = make_media(WORK / "media", find_tool("ffmpeg"))
app = WorkshopArtGUI()
root = app.root
root.report_callback_exception = lambda *exc: tk_errors.append("".join(traceback.format_exception(*exc)))
_log_error = app.logger.error


def _capture_error(message, *args, **kwargs):
    text = message % args if args else str(message)
    if "actualizacion de UI" in text or "Error en tarea" in text:
        tk_errors.append(text)
    _log_error(message, *args, **kwargs)


app.logger.error = _capture_error


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def check(condition, message):
    global passed
    if condition:
        passed += 1
    else:
        failures.append(message)
        print("   FALLO:", message)


def pump(seconds=0.3):
    end = time.time() + seconds
    while time.time() < end:
        root.update()
        time.sleep(0.01)


def wait_for(condition, timeout, what):
    end = time.time() + timeout
    while time.time() < end:
        root.update()
        try:
            if condition():
                return True
        except Exception:
            pass
        time.sleep(0.02)
    check(False, f"tiempo agotado esperando: {what}")
    return False


def job_running():
    return bool(app._cancel_btn.winfo_ismapped())


def wait_job(what, timeout=600):
    wait_for(job_running, 10, f"inicio de {what}")
    wait_for(lambda: not job_running(), timeout, f"fin de {what}")
    pump(0.5)


def windows():
    return [w for w in root.winfo_children() if w.winfo_class() == "Toplevel"
            or w.__class__.__name__ == "CTkToplevel"]


def close_windows():
    for window in windows():
        window.destroy()
    pump(0.2)


def find_button(container, text):
    stack = [container]
    while stack:
        widget = stack.pop()
        if widget.__class__.__name__ == "CTkButton" and text in str(widget.cget("text")):
            return widget
        stack.extend(widget.winfo_children())
    return None


def stage(key, name=None):
    source = MEDIA[key]
    target = WORK / "in" / (name or source.name)
    target.parent.mkdir(exist_ok=True)
    target.write_bytes(source.read_bytes())
    return target


def step(name, function):
    start, n_dialogs, n_errors = time.time(), len(dialogs), len(tk_errors)
    try:
        function()
    except Exception:
        check(False, f"{name}: excepción\n{traceback.format_exc()}")
    for error in tk_errors[n_errors:]:
        check(False, f"{name}: error de Tk/UI: {error[-400:]}")
    for kind, title, message in dialogs[n_dialogs:]:
        if kind == "error":
            check(False, f"{name}: diálogo de error '{title}': {message[:200]}")
    print(f"{name}: {time.time() - start:.1f} s")


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------
def load_files():
    for key in ("gif25", "accents", "vertical", "image"):
        path = stage(key)
        answers["file"] = path
        app.select_file()
        check(app.current_file == path, f"abrir {path.name}")
        if path.suffix in (".gif", ".mp4"):
            wait_for(lambda: len(app._gif_frames) > 1, 30, f"preview animado de {path.name}")
    check(len(app.config.get("ui.recent_files", [])) == 4, "lista de recientes")


def steps_and_color_preview():
    app.load_file(stage("gif25", "colors.gif"))
    for index in range(4):
        app._stepper.select(index)
        pump(0.2)
    app._stepper.select(1)
    wait_for(lambda: len(app._steps[1].color_preview._photos) > 1, 30, "preview de color")


def colors_only():
    source = app.current_file
    app.enhance_colors_only()
    wait_job("solo colores")
    check(app.current_file != source and app.current_file.name.endswith("_enhanced.gif"),
          f"solo colores: {app.current_file}")


def video_to_gif():
    app.load_file(stage("wide_video"))
    app.convert_mp4_to_gif()
    pump(0.5)
    button = find_button(windows()[-1], "Convertir")
    check(button is not None, "botón Convertir")
    button.invoke()
    wait_job("video a GIF")
    check(app.current_file.suffix == ".gif" and "convertido" in str(app.current_file),
          f"video a GIF: {app.current_file}")


def fragments():
    for preset, snippet in (("workshop_5part", "val(480)"), ("artwork_2part", "file_type]').val(3)"),
                            ("screenshot_638", "file_type]').val(5)"), ("panorama_5_630", "image_width")):
        app.fragment_with_preset(preset)
        wait_job(f"fragmentar {preset}")
        pieces = app.processor.list_fragments(app.current_file)
        check(len(pieces) == len(app.processor.preset_config(preset)["parts"]), f"{preset}: piezas")
        check(bool(windows()), f"{preset}: diálogo de resultado")
        close_windows()
        app._stepper.select(3)
        app._copy_steam_js()
        check(snippet in root.clipboard_get(), f"{preset}: JS copiado")
        check(app.current_fragments_preset() == preset, f"{preset}: preset detectado en el paso 4")


def preview_help_language():
    app._open_fragment_preview("workshop_5part")
    pump(1.0)
    check(bool(windows()), "ventana de preview")
    close_windows()
    app.show_help()
    pump(0.5)
    check(bool(windows()), "ventana de ayuda")
    close_windows()
    app.log_message("marca-de-log")
    app._on_language_change("EN")
    pump(1.0)
    check("File" in app._stepper._buttons[0].cget("text"), "interfaz en inglés")
    check("marca-de-log" in app.process_log.get("1.0", "end"), "el log se conserva al cambiar de idioma")
    app._on_language_change("ES")
    pump(1.0)


def ai_and_rife():
    source = stage("gif25", "ai.gif")
    app.load_file(source)
    wait_for(lambda: bool(app.model_combo.cget("values")), 30, "lista de modelos")
    models = [v for v in app.model_combo.cget("values") if v.startswith("realesr-animevideov3-x2")]
    if not models:
        print("   (sin modelos de IA: se omite)")
        return
    app.model_combo.set(models[0])
    app.process_full_ai()
    wait_job("IA", timeout=900)
    check("_AI" in app.current_file.name, f"IA: {app.current_file}")
    pump(1.5)
    check(bool(windows()), "reporte de calidad")
    close_windows()
    if not find_tool("rife-ncnn-vulkan"):
        print("   (RIFE no instalado: se omite)")
        return
    app.load_file(source)
    root.after(800, lambda: find_button(windows()[-1], "RIFE").invoke())
    app.enhance_animation()
    wait_job("RIFE", timeout=900)
    check("rife" in app.current_file.name, f"RIFE: {app.current_file}")


def pipeline_optimizer_zip():
    app.load_file(stage("square", "pipe.gif"))
    app.run_full_pipeline("artwork_4grid")
    wait_job("pipeline", timeout=900)
    close_windows()
    pieces = app.processor.list_fragments(app.current_file)
    check(len(pieces) == 4, "pipeline: 4 piezas")
    answers["files"], answers["float"] = pieces, 0.05
    n_dialogs = len(dialogs)
    app.optimize_to_steam_limit()
    wait_job("optimizar")
    check(any(k in ("info", "warning") for k, _t, _m in dialogs[n_dialogs:]), "resumen del optimizador")
    app.export_steam_pack()
    pump(0.5)
    packs = list(pieces[0].parent.glob("*_steam_pack.zip"))
    check(len(packs) == 1 and "LEEME.txt" in zipfile.ZipFile(packs[0]).namelist(), "export ZIP")


def _windows_titled(title):
    import ctypes
    import ctypes.wintypes as wt
    found = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    def collect(hwnd, _):
        buffer = ctypes.create_unicode_buffer(256)
        ctypes.windll.user32.GetWindowTextW(hwnd, buffer, 256)
        if buffer.value == title and ctypes.windll.user32.IsWindowVisible(hwnd):
            found.append(hwnd)
        return True

    ctypes.windll.user32.EnumWindows(collect, 0)
    return found


def drag_and_drop():
    """Post the same WM_DROPFILES message Explorer sends, with a Unicode file name."""
    if sys.platform != "win32":
        return
    import ctypes
    import struct
    path = stage("gif25", "ドラッグ_canción.gif")
    names = (str(path) + "\0\0").encode("utf-16-le")
    header = struct.pack("<IiiII", 20, 0, 0, 0, 1)  # DROPFILES: pFiles, pt, fNC, fWide=1
    kernel32, user32 = ctypes.windll.kernel32, ctypes.windll.user32
    kernel32.GlobalAlloc.restype = ctypes.c_void_p
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalLock.argtypes = kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    user32.PostMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]
    memory = kernel32.GlobalAlloc(0x0042, len(header) + len(names))  # GMEM_MOVEABLE | GMEM_ZEROINIT
    ctypes.memmove(kernel32.GlobalLock(memory), header + names, len(header) + len(names))
    kernel32.GlobalUnlock(memory)
    user32.PostMessageW(root.winfo_id(), 0x0233, memory, None)  # WM_DROPFILES
    wait_for(lambda: app.current_file == path, 15, "archivo soltado con nombre Unicode")
    check(app.current_file == path, f"arrastrar y soltar: {app.current_file}")


def upload_tool_button():
    """Step 4's Upload Tool button opens the tool with the current fragments.

    Skipped when this check is frozen: the button relaunches the executable
    with --upload-tool, which is WorkshopArt.exe in a real build.
    """
    if sys.platform != "win32" or getattr(sys, "frozen", False):
        return
    app.load_file(stage("gif25", "upload.gif"))
    app.fragment_with_preset("artwork_2part")
    wait_job("fragmentar para el Upload Tool")
    close_windows()
    app._launch_upload_tool()
    wait_for(lambda: _windows_titled("WorkshopArt - Upload Tool"), 60, "ventana del Upload Tool")
    for hwnd in _windows_titled("WorkshopArt - Upload Tool"):
        import ctypes
        ctypes.windll.user32.PostMessageW(hwnd, 0x0010, 0, 0)  # WM_CLOSE
    pump(1.0)


def cancel():
    app.load_file(stage("gif30", "cancel.gif"))
    app.fragment_with_preset("panorama_5_630")
    wait_for(job_running, 10, "inicio de la tarea a cancelar")
    pump(0.5)
    app._on_cancel_processing()
    wait_for(lambda: not job_running(), 120, "cancelación")
    pump(0.5)
    check("Cancel" in app.status_var.get(), f"estado tras cancelar: {app.status_var.get()}")


pump(2.0)
for label, scenario in (("abrir archivos", load_files),
                        ("pasos y preview de color", steps_and_color_preview),
                        ("solo colores", colors_only),
                        ("video a GIF", video_to_gif),
                        ("fragmentar y JS por formato", fragments),
                        ("preview, ayuda e idioma", preview_help_language),
                        ("IA y RIFE", ai_and_rife),
                        ("pipeline, optimizador y ZIP", pipeline_optimizer_zip),
                        ("arrastrar y soltar", drag_and_drop),
                        ("botón Upload Tool", upload_tool_button),
                        ("cancelar", cancel)):
    step(label, scenario)

app.on_closing()
print(f"\n{passed} comprobaciones correctas, {len(failures)} fallos")
for failure in failures:
    print(" -", failure[:600])
sys.exit(1 if failures else 0)

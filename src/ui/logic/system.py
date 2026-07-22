"""ui.logic.system - logging, dependency checks, thread-safe UI plumbing.

Provides the update_queue pattern used by every worker thread: workers call
`self.update_queue.put((fn, args))` and `update_ui_loop` drains it on the
tkinter main thread every 100 ms.
"""
import shutil
import sys
import threading
import webbrowser
from datetime import datetime
from pathlib import Path

import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox

from theme_PRO import Colors, Fonts


class SystemMixin:
    """Logging, dependency checks, status updates and app lifecycle."""

    def setup_logging(self):
        """Configure the stdlib logger and initialise GIF-animation state variables.

        Forces stdout/stderr to UTF-8 on Windows to handle emoji in log messages without
        UnicodeEncodeError. A SafeFilter falls back to ASCII if the stream still can't encode.
        """
        import logging, sys, io
        # Reconfigure stdout/stderr to UTF-8 on Windows so emoji in log messages don't crash.
        try:
            if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
                sys.stdout.reconfigure(encoding='utf-8', errors='replace')
            if sys.stderr and hasattr(sys.stderr, 'reconfigure'):
                sys.stderr.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass

        self.logger = logging.getLogger("WorkshopArtPRO")
        self.logger.setLevel(logging.DEBUG)
        if not self.logger.handlers:
            try:
                stream = sys.stderr if sys.stderr else io.StringIO()
                handler = logging.StreamHandler(stream)
            except Exception:
                handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
            # Defensive filter: downgrade unencodable characters to ASCII replacements.
            class _SafeFilter(logging.Filter):
                def filter(self, record):
                    try:
                        msg = record.getMessage()
                        msg.encode(getattr(stream, 'encoding', 'utf-8') or 'utf-8', errors='strict')
                    except Exception:
                        record.msg = str(record.msg).encode('ascii', errors='replace').decode('ascii')
                        record.args = ()
                    return True
            handler.addFilter(_SafeFilter())
            self.logger.addHandler(handler)

        # GIF preview playback state — updated by _animate_gif and _stop_gif_animation.
        self._gif_frames = []       # list of ImageTk.PhotoImage for the current preview
        self._gif_frame_index = 0   # current frame pointer
        self._gif_frame_delay = 100 # ms between frames (read from GIF metadata)
        self._gif_after_id = None   # handle returned by root.after(), used to cancel the loop

    def create_tooltip(self, widget, text):
        """Attach a frameless Toplevel tooltip to widget, shown on hover.

        The tooltip is stored on the widget itself as `_tooltip` so on_leave can destroy it.
        """
        def on_enter(event):
            tooltip = tk.Toplevel()
            tooltip.wm_overrideredirect(True)  # no title bar or window decorations
            tooltip.wm_geometry(f"+{event.x_root+10}+{event.y_root+10}")

            label = tk.Label(tooltip, text=text,
                           bg=Colors.BG_TERTIARY,
                           fg=Colors.TEXT,
                           font=Fonts.CAPTION,
                           padx=10, pady=5)
            label.pack()

            widget._tooltip = tooltip

        def on_leave(event):
            if hasattr(widget, '_tooltip'):
                widget._tooltip.destroy()
                del widget._tooltip

        widget.bind("<Enter>", on_enter)
        widget.bind("<Leave>", on_leave)

    def darken_color(self, color):
        """Return a hex color string darkened by 20%, used for hover states."""
        color = color.lstrip('#')
        r, g, b = tuple(int(color[i:i+2], 16) for i in (0, 2, 4))
        r = int(r * 0.8)
        g = int(g * 0.8)
        b = int(b * 0.8)
        return f'#{r:02x}{g:02x}{b:02x}'

    @staticmethod
    def _lazy_moviepy():
        """Return moviepy.VideoFileClip, importing it on first call.

        moviepy triggers heavy transitive imports (numpy, imageio, etc.) that add ~2 s to
        startup. Deferring the import to the first video operation keeps the app launch fast.

        Supports both moviepy 1.x (VideoFileClip lives in moviepy.editor) and 2.x
        (moved to the top-level moviepy namespace).
        """
        try:
            from moviepy import VideoFileClip  # moviepy >= 2.0
        except ImportError:
            from moviepy.editor import VideoFileClip  # moviepy 1.x
        return VideoFileClip

    def _run_cancellable(self, process_fn):
        """Run process_fn in a daemon thread, managing cancel-button visibility.

        Uses update_queue to dispatch UI changes (show/hide cancel button) from the worker
        thread safely. Any InterruptedError raised by _raise_if_cancelled is caught here.
        """
        if hasattr(self, '_cancel_event'):
            # Clear before starting so a previous cancel state doesn't bleed into the new job.
            self._cancel_event.clear()
        def wrapper():
            # Show cancel button via update_queue (worker thread -> main thread).
            self.update_queue.put((self._show_cancel_btn, ()))
            try:
                process_fn()
            except InterruptedError:
                self.update_status("Cancelado", 0, "🛑")
                self.log_message("Procesamiento cancelado por el usuario", "WARN")
            finally:
                # Always hide cancel button when the job finishes or errors out.
                self.update_queue.put((self._hide_cancel_btn, ()))
        threading.Thread(target=wrapper, daemon=True).start()

    def _raise_if_cancelled(self):
        """Raise InterruptedError if the user pressed Cancel.

        Call this at the start of each major processing step so the cancel takes effect
        promptly rather than only after the entire job finishes.
        """
        if self._is_cancelled():
            raise InterruptedError("Cancelled by user")

    def _is_cancelled(self):
        """Return True if the cancel event has been set by the cancel button handler."""
        return hasattr(self, '_cancel_event') and self._cancel_event.is_set()

    # Thread-safe messagebox helpers — schedule the dialog on the main thread via root.after(0).
    def _ui_info(self, title, msg):
        self.root.after(0, lambda t=title, m=msg: messagebox.showinfo(t, m))

    def _ui_warn(self, title, msg):
        self.root.after(0, lambda t=title, m=msg: messagebox.showwarning(t, m))

    def _ui_error(self, title, msg):
        self.root.after(0, lambda t=title, m=msg: messagebox.showerror(t, m))


    def update_ui_loop(self):
        """Drain update_queue and call each pending UI function on the main thread.

        This is the core of the thread-safety pattern: worker threads enqueue (fn, args)
        tuples via update_queue.put(); this loop, rescheduled every 100 ms with root.after,
        executes them safely on the tkinter main thread.
        """
        try:
            while not self.update_queue.empty():
                func, args = self.update_queue.get_nowait()
                func(*args)
        except Exception:
            pass

        # Reschedule itself — runs for the entire lifetime of the app.
        self.root.after(100, self.update_ui_loop)

    # Métodos principales de funcionalidad

    def log_message(self, message, level="INFO"):
        """Append a timestamped line to the on-screen process log and the stdlib logger.

        CTkTextbox does not support colour tags, so all levels are plain text in the widget.
        Called from worker threads throughout the codebase, so the widget insert is
        dispatched through update_queue when not on the main thread.
        """
        timestamp = datetime.now().strftime("%H:%M:%S")
        line = f"[{timestamp}] {level}: {message}\n"

        def _append():
            try:
                self.process_log.insert("end", line)
                self.process_log.see("end")  # auto-scroll to keep the latest line visible
            except Exception:
                pass

        if threading.current_thread() is threading.main_thread():
            _append()
        else:
            self.update_queue.put((_append, ()))

        if level == "ERROR":
            self.logger.error(message)
        elif level == "WARNING":
            self.logger.warning(message)
        else:
            self.logger.info(message)

    def update_status(self, message, progress=None, icon="⏳"):
        """Queue a status-bar and progress-bar update (thread-safe via update_queue).

        progress accepts either 0-100 (int/float) or 0.0-1.0; values > 1 are normalised.
        """
        def update():
            self.status_var.set(message)
            self.status_icon.configure(text=icon)
            if progress is not None:
                # CTkProgressBar expects 0.0-1.0; convert if caller passed 0-100.
                self.progress_var.set(progress / 100.0 if progress > 1 else progress)

        self.update_queue.put((update, ()))

    def update_system_status(self, system, status, state="warning"):
        """Queue a colour-coded update for one of the system-status indicator labels.

        system: "gpu" | "ffmpeg" | "models". Called from the check_dependencies thread.
        """
        def update():
            color_map = {
                "success": Colors.SUCCESS,
                "warning": Colors.WARNING,
                "error": Colors.DANGER,
            }
            color = color_map.get(state, Colors.TEXT_MUTED)

            if system == "gpu":
                self.gpu_status_label.configure(text=f"GPU: {status}", text_color=color)
            elif system == "ffmpeg":
                self.ffmpeg_status_label.configure(text=f"FFmpeg: {status}", text_color=color)
            elif system == "models":
                self.models_status_label.configure(text=f"Modelos: {status}", text_color=color)

        self.update_queue.put((update, ()))

    def check_dependencies(self):
        """Run GPU/FFmpeg/gifski/model checks in a background thread and update status labels.

        All UI updates are dispatched through update_system_status (which uses update_queue)
        so this method is safe to call from any thread.
        """
        def check():
            try:
                # GPU result is cached by the processor after the first call.
                self.log_message("Verificando GPU...", "INFO")
                gpu_available, gpu_info = self.processor.check_gpu_available()

                if gpu_available:
                    self._detected_gpu = gpu_info
                    self.update_system_status("gpu", gpu_info, "success")
                    self.log_message(f"GPU detectada: {gpu_info}", "SUCCESS")
                else:
                    self._detected_gpu = None
                    self.update_system_status("gpu", "No detectada", "warning")
                    self.log_message("GPU no detectada — el procesamiento usará CPU (más lento). Si tienes GPU, actualiza los drivers de video.", "WARNING")
                    self.update_status("GPU no detectada — usando CPU", 100, "⚠️")

                # Verificar FFmpeg
                if self.processor.check_ffmpeg():
                    self.update_system_status("ffmpeg", "Disponible", "success")
                    self.log_message("FFmpeg disponible", "SUCCESS")
                else:
                    self.update_system_status("ffmpeg", "No encontrado", "error")
                    self.log_message("FFmpeg no encontrado - Algunas funciones limitadas", "WARNING")

                # Verificar gifski
                if self.processor.check_gifski():
                    self.log_message("gifski disponible — compresión GIF de alta calidad activa", "SUCCESS")
                else:
                    self.log_message(
                        "gifski no encontrado (opcional). "
                        "Descarga gifski.exe desde github.com/ImageOptim/gifski/releases "
                        "y colócalo en SteamWorkshopAppData/ para mejor compresión.", "WARNING"
                    )

                # Verificar modelos
                available_models = self.processor.model_manager.check_available_models()
                if available_models:
                    self.update_system_status("models", f"{len(available_models)}/5 modelos", 
                                            "success" if len(available_models) >= 3 else "warning")
                    self.update_model_combo(available_models)
                    self.log_message(f"{len(available_models)} modelos disponibles", "INFO")
                else:
                    self.update_system_status("models", "No disponibles", "error")
                    self.log_message("No hay modelos disponibles - Descarga necesaria", "WARNING")

            except Exception as e:
                self.log_message(f"Error verificando dependencias: {e}", "ERROR")

        threading.Thread(target=check, daemon=True).start()

    def update_model_combo(self, available_models):
        """Populate the model selector combo box with available model IDs and descriptions.

        Queued via update_queue so it can be called safely from the check_dependencies thread.
        """
        def update():
            model_options = []
            for model_id in available_models:
                info = self.processor.model_manager.get_model_info(model_id)
                desc = info.get('description', model_id)
                model_options.append(f"{model_id} - {desc}")

            self.model_combo.configure(values=model_options)
            if model_options:
                self.model_combo.set(model_options[0])
                self.model_var.set(available_models[0])
                self.update_model_info()
                # Apply the persisted anime/no-anime choice now that the
                # installed-model list is known.
                self.set_content_is_anime(self.config.get("ui.is_anime", True))

        self.update_queue.put((update, ()))

    def update_model_info(self):
        """Refresh the model-info panel below the combo box for the currently selected model."""
        selected = self.model_combo.get()
        if not selected:
            return

        # The combo value format is "model_id - description"; extract just the id.
        model_id = selected.split(" - ")[0]
        info = self.processor.model_manager.get_model_info(model_id)

        # Destroy previous info widgets before rebuilding.
        for widget in self.model_info_frame.winfo_children():
            widget.destroy()

        # Mostrar info del modelo
        info_text = f"Calidad: {info.get('quality_score', 'N/A')}/10 | Velocidad: {info.get('speed_score', 'N/A')}/10"
        ctk.CTkLabel(self.model_info_frame, text=info_text,
                     font=Fonts.CAPTION,
                     text_color=Colors.TEXT_SECONDARY).pack(anchor="w")

        # Mejor para
        best_for = ", ".join(info.get('best_for', []))
        ctk.CTkLabel(self.model_info_frame, text=f"Ideal para: {best_for}",
                     font=Fonts.CAPTION,
                     text_color=Colors.TEXT_SECONDARY).pack(anchor="w", pady=(5, 0))

    # Model preference per user's anime/no-anime choice, best first.
    # Only models actually present on disk are considered.
    _ANIME_MODEL_PRIORITY = (
        "realesr-animevideov3-x4", "realesrgan-x4plus-anime",
        "cugan-se-4x-no-denoise", "realesr-animevideov3-x3",
    )
    _GENERAL_MODEL_PRIORITY = (
        "realesrgan-x4plus", "realesr-general-x4v3", "realesrnet-x4plus",
    )

    def set_content_is_anime(self, is_anime: bool) -> None:
        """Apply the user's anime/no-anime choice: persist it and select the model.

        Replaces the former CV auto-detection, which misclassified too often.
        The user knows what their content is; we just map the answer to the
        best installed model.
        """
        self.config.set("ui.is_anime", bool(is_anime))
        available = self.processor.model_manager.check_available_models()
        priority = (self._ANIME_MODEL_PRIORITY if is_anime
                    else self._GENERAL_MODEL_PRIORITY)
        chosen = next((m for m in priority if m in available), None)
        if chosen is None:
            chosen = available[0] if available else None
        if chosen is None:
            return  # no models installed yet; nothing to select

        def apply():
            try:
                for value in (self.model_combo.cget("values") or []):
                    if str(value).split(" - ")[0] == chosen:
                        self.model_combo.set(value)
                        break
                else:
                    self.model_combo.set(chosen)
                self.model_var.set(chosen)
                self.update_model_info()
            except Exception:
                pass

        self.update_queue.put((apply, ()))
        self.log_message(
            f"Contenido: {'anime' if is_anime else 'no anime'} → modelo {chosen}")

    def download_models(self):
        """Show a confirmation dialog then download all AI models in a background thread.

        Progress is reported through the progress_callback which calls update_status.
        """
        def download():
            try:
                self.update_status("Preparando descarga...", 5, "📥")
                self.log_message("=== DESCARGA DE MODELOS ===", "INFO")
                self.log_message("Tamaño estimado: ~70 MB (Real-ESRGAN ~50 MB + Real-CUGAN ~20 MB)", "INFO")
                self.log_message("Descargando modelos de IA...")

                def progress_callback(message, progress):
                    self.update_status(message, progress, "📥")
                    self.log_message(message)
                    if progress == 100:
                        self.log_message("Descarga completada", "SUCCESS")

                success = self.processor.model_manager.download_all_models(progress_callback)

                if success:
                    self.update_status("¡Modelos descargados!", 100, "✅")
                    self.log_message("=== DESCARGA COMPLETADA ===", "SUCCESS")

                    # Verificar modelos descargados
                    available_models = self.processor.model_manager.check_available_models()
                    self.log_message(f"Modelos disponibles: {len(available_models)}/5", "SUCCESS")

                    for model_id in available_models:
                        info = self.processor.model_manager.get_model_info(model_id)
                        self.log_message(f"✅ {info.get('name', model_id)}", "SUCCESS")

                    self._ui_info("¡Éxito!", 
                        f"¡Descarga completada!\n\n" +
                        f"✅ {len(available_models)} modelos disponibles\n" +
                        f"💾 Ubicación: {self.processor.model_manager.models_dir}\n\n" +
                        f"¡Ya puedes procesar con IA!")

                    # Actualizar lista de modelos
                    self.check_dependencies()
                else:
                    self.update_status("Error en descarga", 0, "❌")
                    self.log_message("Error descargando modelos", "ERROR")
                    self._ui_error("Error", 
                        "Error descargando modelos.\n\n" +
                        "Posibles causas:\n" +
                        "• Sin conexión a internet\n" +
                        "• Firewall bloqueando GitHub\n" +
                        "• Espacio insuficiente en disco\n\n" +
                        "Intenta descargar manualmente desde:\n" +
                        "github.com/xinntao/Real-ESRGAN/releases")

            except Exception as e:
                self.log_message(f"ERROR: {e}", "ERROR")
                self.update_status("Error", 0, "❌")
                self._ui_error("Error", f"Error: {e}")

        if messagebox.askyesno("Confirmar Descarga", 
                              "¿Descargar todos los modelos de IA?\n\n" +
                              "📦 5 modelos especializados:\n" +
                              "• Anime Video v3 (gaming/anime)\n" +
                              "• x4plus (uso general)\n" +
                              "• x4plus Anime (máxima calidad)\n" +
                              "• ESRNet (fotos realistas)\n" +
                              "• x2plus (rápido)\n\n" +
                              "💾 ~70 MB de descarga\n" +
                              "⏱️ 2-5 minutos según conexión\n\n" +
                              "¿Continuar?"):
            threading.Thread(target=download, daemon=True).start()


    def open_steam_tutorial(self):
        """Abrir tutorial de Steam"""
        try:
            webbrowser.open("https://www.youtube.com/watch?v=BQ-9E7sFWc0")
            self.log_message("Tutorial de Steam abierto")
        except Exception as e:
            self.log_message(f"Error abriendo tutorial: {e}", "ERROR")

    def show_help(self):
        """Mostrar ventana de ayuda"""
        from i18n import t
        help_window = ctk.CTkToplevel(self.root)
        help_window.title(t("help_window_title", fallback="Ayuda - WorkshopArt"))
        help_window.geometry("750x700")

        help_window.transient(self.root)
        help_window.grab_set()

        # Contenido de ayuda
        help_text = """WORKSHOPART PRO v1.0 - COMPLETE GUIDE / GUIA COMPLETA

  STEP 1: SELECT FILE / PASO 1: SELECCIONAR ARCHIVO
  - Click "Open file" or drag & drop
  - Supported formats: MP4, AVI, MOV, GIF
  - Auto-detection suggests the best AI model

  STEP 2: CONFIGURE AI / PASO 2: CONFIGURAR IA
  - First time? Download models ("Download AI models" button)
  - Model is auto-selected based on your content
  - Choose GPU for speed or CPU for compatibility

  STEP 3: PROCESS / PASO 3: PROCESAR
  - Process with AI: Upscale 4x with AI (best quality)
  - Colors only: Adjust contrast/saturation without AI (faster)
  - Enhance animation: Interpolate frames for smoother playback

  STEP 4: FRAGMENT / PASO 4: FRAGMENTAR
  Two Steam profile formats available:

  A) WORKSHOP SHOWCASE (5 parts)
     - Splits GIF into 5 horizontal parts
     - Each part: 638x354 px, ~4.6 MB
     - Level 10+ Steam account required

  B) ARTWORK SHOWCASE (2 panels)
     - Main panel: 506x506 px
     - Side strip: 100x506 px
     - Level 10+ Steam account required

  STEP 5: UPLOAD TO STEAM / PASO 5: SUBIR A STEAM
  1. Go to: steamcommunity.com/sharedfiles/edititem/767/3/
  2. Open browser console (F12 > Console tab)
  3. Paste this command and press Enter:

     $J('[name=consumer_app_id]').val(480);
     $J('[name=file_type]').val(0);
     $J('[name=visibility]').val(0);

  4. Fill in the title and description
  5. Upload your GIF file and click Save
  6. Repeat for each fragment

  CONSOLE COMMANDS REFERENCE:
  +-----------------------------------------+----------------------------+
  | Command                                 | Description                |
  +-----------------------------------------+----------------------------+
  | $J('[name=consumer_app_id]').val(480);  | Set game to "Spacewar"     |
  | $J('[name=file_type]').val(0);          | Regular artwork upload      |
  | $J('[name=file_type]').val(11);         | Animated/transparent art   |
  | $J('[name=visibility]').val(0);         | Set visibility to public   |
  +-----------------------------------------+----------------------------+

  PRO TIPS:
  - Use "Auto-detect" for best automatic results
  - GPU is 5-10x faster than CPU
  - For long videos, trim to 5-10 seconds first
  - Apply color adjustments AFTER AI processing

  AI MODELS:
  - Anime Video v3: Best for gaming/anime (RECOMMENDED)
  - x4plus: General purpose, very versatile
  - x4plus Anime: Maximum quality for illustrations
  - ESRNet: Realistic photos and portraits
  - x2plus: 2x upscale, fastest
  - Real-CUGAN SE/Pro: Specialized anime upscaler (Bilibili)

  TROUBLESHOOTING:
  - GPU not detected: Update your graphics drivers
  - Fragmentation fails: Install FFmpeg
  - Models won't download: Check firewall/antivirus
  - Process is slow: Close other applications"""

        # Text widget con scroll
        help_text_widget = ctk.CTkTextbox(
            help_window, font=Fonts.BODY,
            fg_color=Colors.BG_SECONDARY,
            text_color=Colors.TEXT,
            corner_radius=8,
        )
        help_text_widget.pack(fill="both", expand=True, padx=20, pady=20)

        help_text_widget.insert("1.0", help_text)
        help_text_widget.configure(state="disabled")

        ctk.CTkButton(help_window, text=t("close_btn", fallback="Cerrar"),
                      command=help_window.destroy,
                      fg_color=Colors.ACCENT,
                      hover_color=Colors.ACCENT_DARK,
                      height=34, corner_radius=8).pack(pady=(0, 15))

    def on_closing(self):
        """Handle window close: stop animation, clean temp files, then destroy the root window."""
        try:
            self._stop_gif_animation()
            # Temp dir path differs between the compiled exe and the dev environment.
            if getattr(sys, 'frozen', False):
                temp_dir = Path(sys.executable).parent / "SteamWorkshopAppData" / "temp"
            else:
                temp_dir = Path("SteamWorkshopAppData/temp")
            if temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)

            self.log_message("Aplicacion cerrada correctamente")
        except Exception:
            pass

        self.root.destroy()

    def run(self):
        """Ejecutar la aplicación"""
        # Configurar protocolo de cierre
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        # Mensaje de bienvenida
        self.log_message("WorkshopArt v2.0 iniciado", "SUCCESS")
        self.log_message("✨ Versión modular con todas las funciones", "INFO")
        self.log_message("📁 Selecciona un archivo para comenzar", "INFO")

        # Ejecutar loop principal
        self.root.mainloop()



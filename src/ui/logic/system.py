"""ui.logic.system - logging, dependency checks, thread-safe UI plumbing, help.

Worker threads never touch widgets: they call ``self.update_queue.put((fn, args))``
and ``update_ui_loop`` runs the queued callables on the tkinter main thread
every 100 ms. The helpers in this mixin (log_message, update_status, _ui_info,
...) already do that, so they can be called from any thread.
"""
import logging
import shutil
import threading
import traceback
from datetime import datetime

import customtkinter as ctk
from tkinter import messagebox

from app_paths import APP_VERSION, TEMP_DIR
from i18n import t
from ui import theme
from ui.theme import Colors

logger = logging.getLogger("WorkshopArt")


class SystemMixin:
    """Logging, dependency checks, status updates and app lifecycle."""

    def setup_logging(self):
        """Attach a stderr handler to the app logger (stderr is the runtime log when frozen)."""
        import sys
        self.logger = logger
        logger.setLevel(logging.INFO)
        if not logger.handlers:
            handler = logging.StreamHandler(sys.stderr)
            handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
            logger.addHandler(handler)

        # GIF preview playback state - see FilesMixin._animate_gif.
        self._gif_frames = []
        self._gif_frame_index = 0
        self._gif_frame_delay = 100
        self._gif_after_id = None

    # ------------------------------------------------------------------
    # Background jobs
    # ------------------------------------------------------------------
    def _run_cancellable(self, process_fn, error_title=None):
        """Run ``process_fn`` in a daemon thread with the Cancel button visible.

        InterruptedError (Cancel pressed) and any other exception are handled
        here: the status bar, the log and an error dialog report them.
        """
        self._cancel_event.clear()

        def wrapper():
            self.update_queue.put((self._show_cancel_btn, ()))
            try:
                process_fn()
            except InterruptedError:
                self.update_status(t("status_cancelled", fallback="Cancelado"), 0, "🛑")
                self.log_message("Proceso cancelado por el usuario", "WARNING")
            except Exception as e:
                self.logger.error("Error en tarea: %s\n%s", e, traceback.format_exc())
                self.update_status(t("status_error", fallback="Error"), 0, "❌")
                self.log_message(f"ERROR: {e}", "ERROR")
                self._ui_error(error_title or t("error_title", fallback="Error"), str(e))
            finally:
                self.update_queue.put((self._hide_cancel_btn, ()))

        threading.Thread(target=wrapper, daemon=True).start()

    def _raise_if_cancelled(self):
        """Raise InterruptedError if the user pressed Cancel."""
        if self._is_cancelled():
            raise InterruptedError(t("status_cancelled", fallback="Cancelado"))

    def _is_cancelled(self):
        return self._cancel_event.is_set()

    # Thread-safe dialogs: always shown from the main thread.
    def _ui_info(self, title, msg):
        self.update_queue.put((lambda: messagebox.showinfo(title, msg, parent=self.root), ()))

    def _ui_warn(self, title, msg):
        self.update_queue.put((lambda: messagebox.showwarning(title, msg, parent=self.root), ()))

    def _ui_error(self, title, msg):
        self.update_queue.put((lambda: messagebox.showerror(title, msg, parent=self.root), ()))

    def update_ui_loop(self):
        """Run the callables queued by worker threads, then reschedule (every 100 ms)."""
        while not self.update_queue.empty():
            try:
                func, args = self.update_queue.get_nowait()
                func(*args)
            except Exception:
                self.logger.error("Error en actualizacion de UI:\n%s", traceback.format_exc())
        self.root.after(100, self.update_ui_loop)

    # ------------------------------------------------------------------
    # Log and status bar
    # ------------------------------------------------------------------
    def log_message(self, message, level="INFO"):
        """Append a timestamped line to the process log panel and the runtime log."""
        line = f"[{datetime.now():%H:%M:%S}] {level}: {message}\n"

        def append():
            try:
                self.process_log.insert("end", line)
                self.process_log.see("end")
            except Exception:
                pass  # panel rebuilt (language change) or window closing

        if threading.current_thread() is threading.main_thread():
            append()
        else:
            self.update_queue.put((append, ()))
        if level == "ERROR":
            self.logger.error(message)
        elif level == "WARNING":
            self.logger.warning(message)
        else:
            self.logger.info(message)

    def update_status(self, message, progress=None, icon="⏳"):
        """Queue a status-bar update. ``progress`` is 0-100 (or 0-1), None keeps it."""
        def update():
            self.status_var.set(message)
            self.status_icon.configure(text=icon)
            if progress is not None:
                self.progress_var.set(progress / 100.0 if progress > 1 else progress)

        self.update_queue.put((update, ()))

    def update_system_status(self, system, status, state="warning"):
        """Colour-coded update of one status-bar indicator ("gpu", "ffmpeg", "models")."""
        labels = {
            "gpu": ("gpu_status_label", "GPU"),
            "ffmpeg": ("ffmpeg_status_label", "FFmpeg"),
            "models": ("models_status_label", t("models_label", fallback="Modelos")),
        }
        color = {"success": Colors.SUCCESS, "warning": Colors.WARNING,
                 "error": Colors.DANGER}.get(state, Colors.TEXT_MUTED)

        def update():
            attr, prefix = labels[system]
            getattr(self, attr).configure(text=f"{prefix}: {status}", text_color=color)

        self.update_queue.put((update, ()))

    # ------------------------------------------------------------------
    # Dependencies and AI models
    # ------------------------------------------------------------------
    def check_dependencies(self):
        """Check GPU, FFmpeg, gifski and AI models in a background thread."""
        def check():
            try:
                gpu_ok, gpu_info = self.processor.check_gpu_available()
                self._detected_gpu = gpu_info if gpu_ok else None
                if gpu_ok:
                    self.update_system_status("gpu", gpu_info, "success")
                    self.log_message(f"GPU: {gpu_info}")
                else:
                    self.update_system_status("gpu", t("not_detected", fallback="No detectada"))
                    self.log_message("No se detecto GPU: la IA usara la CPU (mas lento). "
                                     "Si tienes GPU, actualiza los drivers.", "WARNING")

                if self.processor.check_ffmpeg():
                    self.update_system_status("ffmpeg", t("available", fallback="OK"), "success")
                else:
                    self.update_system_status("ffmpeg", t("not_found", fallback="No encontrado"), "error")
                    self.log_message("FFmpeg no encontrado: reinicia la app para descargarlo", "ERROR")

                if not self.processor.check_gifski():
                    self.log_message("gifski no encontrado: se usara FFmpeg (fragmentos algo "
                                     "mas pesados). Reinicia la app para descargarlo.", "WARNING")

                models = self.processor.model_manager.check_available_models()
                if models:
                    self.update_system_status("models", str(len(models)), "success")
                    self.update_model_combo(models)
                else:
                    self.update_system_status("models", "0", "error")
                    self.log_message("No hay modelos de IA: usa 'Descargar modelos' en el paso 2",
                                     "WARNING")
            except Exception as e:
                self.log_message(f"Error comprobando dependencias: {e}", "ERROR")

        threading.Thread(target=check, daemon=True).start()

    def selected_model_id(self) -> str:
        """Model id of the selector entry ("id - description")."""
        return self.model_var.get().split(" - ")[0].strip()

    def update_model_combo(self, available_models):
        """Fill the model selector with "id - description" entries (thread-safe)."""
        def update():
            options = []
            for model_id in available_models:
                info = self.processor.model_manager.get_model_info(model_id)
                description = t(f"model_desc_{model_id}", fallback=info.get("description", model_id))
                options.append(f"{model_id} - {description}")
            self.model_combo.configure(values=options)
            if options:
                self.set_content_is_anime(self.config.get("ui.is_anime", True))

        self.update_queue.put((update, ()))

    def update_model_info(self):
        """Refresh the quality/speed summary below the model selector."""
        selected = self.model_combo.get()
        if not selected:
            return
        model_id = selected.split(" - ")[0]
        info = self.processor.model_manager.get_model_info(model_id)
        for widget in self.model_info_frame.winfo_children():
            widget.destroy()
        text = t("model_scores", fallback="Calidad: {q}/10 | Velocidad: {s}/10",
                 q=info.get("quality_score", "?"), s=info.get("speed_score", "?"))
        ctk.CTkLabel(self.model_info_frame, text=text, justify="left",
                     font=theme.font("CAPTION"),
                     text_color=Colors.TEXT_SECONDARY).pack(anchor="w")

    # Model preference per the user's anime/no-anime answer, best first.
    _ANIME_MODEL_PRIORITY = (
        "realesr-animevideov3-x4", "realesrgan-x4plus-anime",
        "cugan-se-4x-no-denoise", "realesr-animevideov3-x3",
    )
    _GENERAL_MODEL_PRIORITY = (
        "realesrgan-x4plus", "realesr-general-x4v3", "realesrnet-x4plus",
    )

    def set_content_is_anime(self, is_anime: bool) -> None:
        """Persist the anime/no-anime answer and select the best installed model for it."""
        self.config.set("ui.is_anime", bool(is_anime))
        available = self.processor.model_manager.check_available_models()
        priority = self._ANIME_MODEL_PRIORITY if is_anime else self._GENERAL_MODEL_PRIORITY
        chosen = next((m for m in priority if m in available), available[0] if available else None)
        if chosen is None:
            return

        def apply():
            for value in self.model_combo.cget("values") or []:
                if str(value).split(" - ")[0] == chosen:
                    self.model_combo.set(value)
                    break
            self.update_model_info()

        self.update_queue.put((apply, ()))
        self.log_message(f"Contenido {'anime' if is_anime else 'no anime'}: modelo {chosen}")

    def download_models(self):
        """Download Real-ESRGAN and Real-CUGAN after confirmation (background thread)."""
        if not messagebox.askyesno(
                t("download_models", fallback="Descargar modelos"),
                t("download_models_confirm",
                  fallback="Se descargarán los modelos de IA (unos 90 MB):\n\n"
                           "• Real-ESRGAN: Anime Video v3 (2x, 3x, 4x), x4plus Anime y x4plus\n"
                           "• Real-CUGAN: modelos anime SE (2x, 3x, 4x)\n\n"
                           "¿Continuar?"),
                parent=self.root):
            return

        def download():
            def progress(message, percent):
                self.update_status(message, percent, "📥")

            manager = self.processor.model_manager
            if manager.download_all_models(progress):
                # The processor caches tool paths: refresh them after the download.
                self.processor.realesrgan_path = manager.exe_path
                self.processor.realcugan_path = manager.cugan_exe_path
                models = manager.check_available_models()
                self.update_status(t("models_ready", fallback="Modelos descargados"), 100, "✅")
                self.log_message(f"Modelos disponibles: {', '.join(models)}", "SUCCESS")
                self._ui_info(t("download_models", fallback="Descargar modelos"),
                              t("models_ready_msg", fallback="{n} modelos listos en:\n{path}",
                                n=len(models), path=manager.models_dir))
                self.check_dependencies()
            else:
                self.update_status(t("status_error", fallback="Error"), 0, "❌")
                self._ui_error(t("download_models", fallback="Descargar modelos"),
                               t("models_download_failed",
                                 fallback="No se pudieron descargar los modelos.\n\n"
                                          "Comprueba la conexión a internet o el firewall.\n"
                                          "Detalles en el log de proceso."))

        threading.Thread(target=download, daemon=True).start()

    # ------------------------------------------------------------------
    # Help and lifecycle
    # ------------------------------------------------------------------
    def show_help(self):
        """Open the help window (translated guide of the 4-step workflow)."""
        window = ctk.CTkToplevel(self.root)
        window.title(t("help_window_title", fallback="Ayuda - WorkshopArt"))
        window.geometry("760x680")
        window.transient(self.root)
        window.after(50, window.grab_set)

        box = ctk.CTkTextbox(window, font=theme.font("BODY"), wrap="word",
                             fg_color=Colors.BG_SECONDARY, text_color=Colors.TEXT,
                             corner_radius=8)
        box.pack(fill="both", expand=True, padx=20, pady=(20, 10))
        box.insert("1.0", t("help_text", fallback="", version=APP_VERSION))
        box.configure(state="disabled")
        ctk.CTkButton(window, text=t("close_btn", fallback="Cerrar"), command=window.destroy,
                      fg_color=Colors.ACCENT, hover_color=Colors.ACCENT_DARK,
                      height=34, corner_radius=8).pack(pady=(0, 15))

    def on_closing(self):
        """Stop the preview animation, remove temporary files and close."""
        try:
            self._stop_gif_animation()
            shutil.rmtree(TEMP_DIR, ignore_errors=True)
        except Exception:
            pass
        self.root.destroy()

    def run(self):
        """Start the tkinter main loop."""
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.log_message(f"WorkshopArt v{APP_VERSION} iniciado")
        self.root.mainloop()

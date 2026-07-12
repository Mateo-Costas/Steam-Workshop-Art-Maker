"""
gui_methods.py — GUIMethodsMixin: all business-logic methods for the WorkshopArt GUI.

Architecture notes:
- This is a Mixin class mixed into the main App class, keeping GUI layout separate from logic.
- Thread safety: worker threads must never touch tkinter widgets directly. Instead, they call
  `self.update_queue.put((fn, args))`, and `update_ui_loop` drains the queue every 100 ms on
  the main thread. Any method that updates widgets from a thread must use this pattern.
- Cancel flow: `_run_cancellable` spawns a daemon thread and clears `_cancel_event` before
  starting. Worker functions call `_raise_if_cancelled()` at checkpoints; it raises
  InterruptedError which `_run_cancellable`'s wrapper catches and shows a "Cancelled" status.
- Lazy imports: moviepy is imported on first use via `_lazy_moviepy()` to avoid a ~2 s startup
  penalty from moviepy's heavy transitive imports.
- PRO patch: at module bottom, `_pro_features.py` (not shipped in the public repo) replaces
  stub methods with the real AI-processing implementations when present.
"""
import sys
import gc
import io
import os
import uuid
import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox, filedialog
from datetime import datetime
import threading
from pathlib import Path
from PIL import Image, ImageTk, ImageSequence, ImageEnhance
from typing import Optional
import shutil
import webbrowser
import subprocess
import platform
from theme_PRO import Colors, Fonts
from analyzers import ContentAnalyzer as _ContentAnalyzer

# Hide subprocess console windows on Windows
# Suppress the console window that Windows spawns for subprocess calls.
_NO_WINDOW_FLAGS = {'creationflags': subprocess.CREATE_NO_WINDOW} if platform.system() == 'Windows' else {}

# Used throughout to distinguish static images from animated formats.
_STATIC_IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.bmp', '.webp'}


def _steam_format_suggestion(w: int, h: int) -> Optional[str]:
    """Delegates to ContentAnalyzer._get_upload_suggestion — single source of truth."""
    if h <= 0:
        return None
    return _ContentAnalyzer._get_upload_suggestion(w, h)


class GUIMethodsMixin:
    """Mixin providing all processing/business-logic methods for the WorkshopArt GUI.

    Must be mixed in alongside a tkinter root that exposes `self.root`, `self.update_queue`,
    and the various widget attributes (status_var, progress_var, process_log, etc.).
    """

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
        """
        from moviepy.editor import VideoFileClip
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

    def _launch_upload_tool(self, fragments=None, preset: str = None):
        """Launch the Upload Tool as a subprocess, passing fragment paths and preset as CLI args.

        In frozen (compiled) mode, re-invokes the same .exe with --upload-tool. In dev mode,
        looks for upload_tool.py two levels up; if absent, shows the PRO upgrade prompt.
        """
        try:
            flags = _NO_WINDOW_FLAGS
            extra = []
            if fragments:
                extra += ["--fragments"] + [str(f) for f in fragments]
            if preset:
                extra += ["--preset", preset]
            if getattr(sys, 'frozen', False):
                # Running as a compiled .exe — pass a flag to the same binary.
                subprocess.Popen([sys.executable, "--upload-tool"] + extra, **flags)
            else:
                upload_tool_path = Path(__file__).parent.parent / "upload_tool.py"
                if not upload_tool_path.exists():
                    # upload_tool.py is not included in the public repo — show upgrade prompt.
                    messagebox.showinfo(
                        "WorkshopArt PRO",
                        "El Upload Tool automatico es una funcion exclusiva de la version PRO.\n\n"
                        "Descarga el .exe compilado en:\n"
                        "https://mxteoo7.itch.io/workshopart-pro\n\n"
                        "La version gratuita incluye todos los presets y procesamiento IA.\n"
                        "Puedes subir los fragmentos manualmente siguiendo las instrucciones del README."
                    )
                    return
                subprocess.Popen([sys.executable, str(upload_tool_path)] + extra,
                                 cwd=str(upload_tool_path.parent), **flags)
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo abrir el Upload Tool:\n{e}")

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

    def select_file(self):
        """Open a file dialog to pick the source media file.

        Sets self.current_file and triggers show_file_info(). If auto-detect is enabled,
        also runs analyze_content() to recommend an AI model.
        """
        filetypes = [
            ("Archivos multimedia", "*.mp4 *.avi *.mov *.mkv *.webm *.m4v *.flv *.gif *.jpg *.jpeg *.png *.bmp *.webp"),
            ("Imagenes", "*.jpg *.jpeg *.png *.bmp *.webp"),
            ("Videos", "*.mp4 *.avi *.mov *.mkv *.webm *.m4v *.flv"),
            ("GIFs", "*.gif"),
            ("Todos", "*.*")
        ]

        filename = filedialog.askopenfilename(title="Seleccionar archivo", filetypes=filetypes)

        if filename:
            self.current_file = Path(filename)
            self.show_file_info()

            if self.auto_detect_var.get():
                self.analyze_content()

    # PARTE 2/3 - CONTINÚA DESDE select_file()

    def _stop_gif_animation(self):
        """Cancel the pending root.after callback and clear the frame list.

        Must be called before starting a new preview to avoid two animation loops running
        concurrently on the same label.
        """
        if hasattr(self, '_gif_after_id') and self._gif_after_id:
            try:
                self.root.after_cancel(self._gif_after_id)
            except Exception:
                pass
            self._gif_after_id = None
        self._gif_frames = []
        self._gif_frame_index = 0

    # Video preview memory/performance limits. PhotoImage objects are kept in RAM for the
    # entire preview loop, so _VIDEO_PREVIEW_MAX_FRAMES is the hard cap on peak usage.
    _VIDEO_PREVIEW_MAX_FRAMES = 240      # max PhotoImage objects held in memory at once
    _VIDEO_PREVIEW_MIN_FPS = 8           # below this the preview looks choppy
    _VIDEO_PREVIEW_MAX_FPS = 24          # higher fps gives no visible benefit for a preview
    _VIDEO_PREVIEW_THUMB = (375, 250)    # thumbnail dimensions for the preview widget

    def _build_video_preview(self, preview_frame):
        """Construir preview animado de un video reproduciéndolo entero en loop.

        - Muestrea toda la duración (no recorta a los primeros N segundos).
        - Ajusta fps dinámicamente para no exceder _VIDEO_PREVIEW_MAX_FRAMES.
        - Lee secuencialmente con iter_frames (mucho más rápido que get_frame uno a uno).
        - Corre en background para no bloquear la UI con videos largos.
        """
        video_file = self.current_file

        # Placeholder mientras se decodifica
        placeholder = ctk.CTkLabel(preview_frame, text="⏳ Generando preview...",
                                   width=self._VIDEO_PREVIEW_THUMB[0],
                                   height=self._VIDEO_PREVIEW_THUMB[1])
        placeholder.pack()

        def worker():
            try:
                VideoFileClip = self._lazy_moviepy()
                frames = []
                delay_ms = 67  # fallback ~15 fps

                with VideoFileClip(str(video_file)) as clip:
                    duration = float(clip.duration or 0)
                    if duration <= 0:
                        raise ValueError("Duración desconocida")

                    # Compute fps that covers the full duration without exceeding the frame cap.
                    target_fps = self._VIDEO_PREVIEW_MAX_FRAMES / duration
                    target_fps = max(self._VIDEO_PREVIEW_MIN_FPS,
                                     min(self._VIDEO_PREVIEW_MAX_FPS, target_fps))
                    delay_ms = max(20, int(1000 / target_fps))

                    thumb = self._VIDEO_PREVIEW_THUMB
                    for i, arr in enumerate(clip.iter_frames(fps=target_fps, dtype='uint8')):
                        if i >= self._VIDEO_PREVIEW_MAX_FRAMES:
                            break
                        # User switched file while we were decoding — discard work and abort.
                        if self.current_file != video_file:
                            return
                        frame_img = Image.fromarray(arr)
                        frame_img.thumbnail(thumb, Image.Resampling.LANCZOS)
                        frames.append(frame_img.convert('RGBA'))

                # Hand off to main thread: ImageTk.PhotoImage must be created on the main thread.
                def install():
                    if self.current_file != video_file:
                        return
                    if not placeholder.winfo_exists():
                        return
                    try:
                        self._stop_gif_animation()
                        self._gif_frames = [ImageTk.PhotoImage(img) for img in frames]
                        self._gif_frame_index = 0
                        self._gif_frame_delay = delay_ms
                        if not self._gif_frames:
                            placeholder.configure(text="(preview vacío)")
                            return
                        placeholder.destroy()
                        label = ctk.CTkLabel(preview_frame, text="", image=self._gif_frames[0])
                        label.image = self._gif_frames[0]  # prevent garbage collection by tkinter
                        label.pack()
                        if len(self._gif_frames) > 1:
                            self._gif_after_id = self.root.after(
                                self._gif_frame_delay, self._animate_gif, label)
                    except Exception as e:
                        self.log_message(f"Error mostrando preview: {e}", "WARNING")
                    finally:
                        # PIL source images can be freed; PhotoImage already copied the pixel data.
                        frames.clear()
                        gc.collect()

                self.update_queue.put((install, ()))
            except Exception as e:
                self.log_message(f"No se pudo generar preview del video: {e}", "WARNING")
                def fail():
                    if placeholder.winfo_exists():
                        placeholder.configure(text="(preview no disponible)")
                self.update_queue.put((fail, ()))

        threading.Thread(target=worker, daemon=True).start()

    def _animate_gif(self, label):
        """Advance to the next preview frame and reschedule itself via root.after.

        Runs only on the main thread (scheduled by root.after). Stops silently if the label
        is destroyed (user switched file) or the frame list is cleared by _stop_gif_animation.
        """
        try:
            frames = self._gif_frames
            if not frames or not label.winfo_exists():
                return
            self._gif_frame_index = (self._gif_frame_index + 1) % len(frames)
            photo = frames[self._gif_frame_index]
            label.configure(image=photo)
            label.image = photo  # prevent garbage collection
            # Store the after-id so _stop_gif_animation can cancel this pending call.
            self._gif_after_id = self.root.after(self._gif_frame_delay, self._animate_gif, label)
        except Exception:
            pass

    def show_file_info(self):
        """Render file metadata and an animated preview in the file-info panel.

        GIF and video previews are decoded in background threads to avoid freezing the UI.
        Each branch follows the same pattern: show a placeholder, decode in a thread, then
        install the frames via update_queue on the main thread.
        """
        if not self.current_file:
            return

        self._stop_gif_animation()

        # Clear any previously displayed file info before rebuilding.
        for widget in self.file_info_frame.winfo_children():
            widget.destroy()

        # Frame para preview y detalles
        content_frame = ctk.CTkFrame(self.file_info_frame, fg_color="transparent")
        content_frame.pack(fill="x")

        try:
            # Preview thumbnail
            preview_frame = ctk.CTkFrame(content_frame, fg_color="transparent")
            preview_frame.pack(side="left", padx=(0, 15))

            ext = self.current_file.suffix.lower()

            if ext == '.gif':
                # Decode GIF frames in a background thread (same pattern as _build_video_preview).
                gif_file = self.current_file
                placeholder = ctk.CTkLabel(preview_frame, text="⏳ Cargando preview...",
                                           width=375, height=130)
                placeholder.pack()

                def _load_gif_preview():
                    MAX_PREVIEW_FRAMES = 60
                    try:
                        raw = gif_file.read_bytes()
                        # Some encoders write a stray 0x21 extension block after the trailer;
                        # PIL chokes on it, so patch the last byte to 0x3B (GIF trailer).
                        if raw and raw[-1] == 0x21:
                            raw = raw[:-1] + b"\x3B"
                        src = io.BytesIO(raw)
                        pil_frames = []
                        delay_ms = 100
                        with Image.open(src) as gif_img:
                            delay_ms = gif_img.info.get('duration', 100)
                            if delay_ms < 20:
                                delay_ms = 100
                            for i, frame in enumerate(ImageSequence.Iterator(gif_img)):
                                if i >= MAX_PREVIEW_FRAMES:
                                    break
                                if self.current_file != gif_file:
                                    return  # user switched file — abort
                                resized = frame.convert('RGBA')
                                resized.thumbnail((375, 250), Image.Resampling.LANCZOS)
                                pil_frames.append(resized)
                        gc.collect()

                        # Install frames on the main thread via update_queue.
                        def install():
                            if self.current_file != gif_file:
                                return  # user switched file — discard
                            if not placeholder.winfo_exists():
                                return
                            try:
                                self._stop_gif_animation()
                                # PhotoImage must be created on the main thread.
                                self._gif_frames = [ImageTk.PhotoImage(f) for f in pil_frames]
                                self._gif_frame_index = 0
                                self._gif_frame_delay = delay_ms
                                if not self._gif_frames:
                                    placeholder.configure(text="(preview vacío)")
                                    return
                                placeholder.destroy()
                                lbl = ctk.CTkLabel(preview_frame, text="",
                                                   image=self._gif_frames[0])
                                lbl.image = self._gif_frames[0]  # prevent GC
                                lbl.pack()
                                if len(self._gif_frames) > 1:
                                    self._gif_after_id = self.root.after(
                                        self._gif_frame_delay, self._animate_gif, lbl)
                            except Exception as e:
                                self.log_message(f"Error mostrando preview GIF: {e}", "WARNING")
                            finally:
                                # PIL frames are no longer needed; PhotoImage has the pixel data.
                                pil_frames.clear()
                                gc.collect()

                        self.update_queue.put((install, ()))
                    except Exception as e:
                        def _fail():
                            if placeholder.winfo_exists():
                                placeholder.configure(text="(preview no disponible)")
                        self.update_queue.put((_fail, ()))

                threading.Thread(target=_load_gif_preview, daemon=True).start()

            elif ext in ('.jpg', '.jpeg', '.png', '.bmp', '.webp'):
                # Static image: decode synchronously (fast) and display directly.
                try:
                    with Image.open(self.current_file) as img:
                        img_preview = img.copy()
                    img_preview.thumbnail((375, 250), Image.Resampling.LANCZOS)
                    photo = ImageTk.PhotoImage(img_preview.convert('RGBA'))
                    preview_label = ctk.CTkLabel(preview_frame, text="", image=photo)
                    preview_label.image = photo  # prevent GC
                    preview_label.pack()
                except Exception:
                    pass

            elif ext in ('.mp4', '.avi', '.mov', '.mkv', '.webm', '.m4v', '.flv'):
                # Animated video preview — decoded in background, see _build_video_preview.
                self._build_video_preview(preview_frame)

            # Informacion del archivo
            info_frame = ctk.CTkFrame(content_frame, fg_color="transparent")
            info_frame.pack(side="left", fill="both", expand=True)

            ctk.CTkLabel(info_frame, text=self.current_file.name,
                         font=("Segoe UI", 11, "bold"),
                         text_color=Colors.TEXT).pack(anchor="w")

            size_mb = self.current_file.stat().st_size / (1024 * 1024)
            details_text = f"Tamano: {size_mb:.2f} MB"

            if ext == '.gif':
                try:
                    _g_bytes = self.current_file.read_bytes()
                    # Apply the same trailing-byte fix used in the preview loader.
                    if _g_bytes and _g_bytes[-1] == 0x21:
                        _g_target = io.BytesIO(_g_bytes[:-1] + b"\x3B")
                    else:
                        _g_target = self.current_file
                    with Image.open(_g_target) as img:
                        details_text += f"\nDimensiones: {img.size[0]}x{img.size[1]}"
                        details_text += f"\nFrames: {getattr(img, 'n_frames', 1)}"
                        duration = img.info.get('duration', 100)
                        fps = 1000 / duration if duration > 0 else 10
                        details_text += f"\nFPS: {fps:.1f}"
                        _sug = _steam_format_suggestion(img.size[0], img.size[1])
                        if _sug:
                            details_text += f"\nSugerido: {_sug}"
                except Exception as _gif_err:
                    details_text += f"\n(info GIF no disponible: {_gif_err})"

            elif ext in ('.jpg', '.jpeg', '.png', '.bmp', '.webp'):
                with Image.open(self.current_file) as img:
                    details_text += f"\nDimensiones: {img.size[0]}x{img.size[1]}"
                    details_text += f"\nFormato: {img.format or ext.upper().lstrip('.')}"
                    details_text += f"\nModo: {img.mode}"
                    _sug = _steam_format_suggestion(img.size[0], img.size[1])
                    if _sug:
                        details_text += f"\nSugerido: {_sug}"

            elif ext in ('.mp4', '.avi', '.mov'):
                try:
                    VideoFileClip = self._lazy_moviepy()
                    with VideoFileClip(str(self.current_file)) as clip:
                        details_text += f"\nDimensiones: {clip.w}x{clip.h}"
                        details_text += f"\nDuracion: {clip.duration:.1f}s"
                        details_text += f"\nFPS: {clip.fps:.1f}"
                        _sug = _steam_format_suggestion(clip.w, clip.h)
                        if _sug:
                            details_text += f"\nSugerido: {_sug}"
                except Exception:
                    details_text += "\nNo se pudo leer info del video"

            ctk.CTkLabel(info_frame, text=details_text,
                         font=Fonts.CAPTION,
                         text_color=Colors.TEXT_SECONDARY,
                         justify="left").pack(anchor="w", pady=(5, 0))

            _ct_text = ""
            if hasattr(self, 'content_analysis') and self.content_analysis:
                _ct = self.content_analysis.get('type', 'unknown')
                _cf = self.content_analysis.get('confidence', 0) * 100
                _ct_text = f"Tipo: {_ct} ({_cf:.0f}%)"
            self._content_type_label = ctk.CTkLabel(
                info_frame, text=_ct_text,
                font=("Segoe UI", 9, "bold"),
                text_color=Colors.ACCENT)
            self._content_type_label.pack(anchor="w", pady=(10, 0))

            self.log_message(f"Archivo seleccionado: {self.current_file.name}")
            self.update_status("Archivo cargado", 100, "✅")

        except Exception as e:
            ctk.CTkLabel(self.file_info_frame, text=f"Error: {e}",
                         text_color=Colors.DANGER).pack(anchor="w")
            self.log_message(f"Error mostrando info del archivo: {e}", "ERROR")

    def analyze_content(self):
        """Run content-type analysis in a background thread and auto-select the best AI model.

        Stores the result in self.content_analysis. All UI updates go through update_queue.
        """
        if not self.current_file:
            return

        def analyze():
            try:
                self.update_status("Analizando contenido...", 50, "🔍")
                self.log_message("Analizando tipo de contenido...")

                self.content_analysis = self.processor.content_analyzer.analyze_content(self.current_file)
                recommended_model = self.processor.model_manager.get_model_recommendation(self.content_analysis)

                def update_ui():
                    # Actualizar selector de modelo
                    try:
                        current_values = self.model_combo.cget("values") or []
                    except Exception:
                        current_values = []
                    for value in current_values:
                        if recommended_model in str(value):
                            self.model_combo.set(value)
                            self.model_var.set(recommended_model)
                            self.update_model_info()
                            break

                    # Actualizar etiqueta de tipo de contenido en el panel existente
                    content_type = self.content_analysis.get('type', 'unknown')
                    confidence = self.content_analysis.get('confidence', 0) * 100
                    if hasattr(self, '_content_type_label'):
                        try:
                            self._content_type_label.configure(
                                text=f"Tipo: {content_type} ({confidence:.0f}%)")
                        except Exception:
                            pass

                    # Log
                    self.log_message(f"Tipo detectado: {content_type}", "SUCCESS")
                    self.log_message(f"Modelo recomendado: {recommended_model}", "SUCCESS")

                self.update_queue.put((update_ui, ()))
                self.update_status("Análisis completado", 100, "✅")

            except Exception as e:
                self.log_message(f"Error analizando contenido: {e}", "ERROR")
                self.update_status("Error en análisis", 0, "❌")

        threading.Thread(target=analyze, daemon=True).start()

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

    def process_full_ai(self):
        """Stub: AI upscaling (Real-ESRGAN/Real-CUGAN) — replaced by the PRO patch at module load."""
        messagebox.showinfo(
            "WorkshopArt PRO",
            "El procesamiento con IA (Real-ESRGAN / Real-CUGAN) es una funcion exclusiva de la version PRO.\n\n"
            "Descarga el .exe compilado en:\n"
            "https://mxteoo7.itch.io/workshopart-pro\n\n"
            "La version gratuita incluye conversion MP4-a-GIF, mejora de colores,\n"
            "mejora de animacion y fragmentacion para todos los presets de Steam."
        )



    def enhance_colors_only(self):
        """Apply contrast/saturation/vibrance/sharpness/temperature adjustments without AI.

        Runs via _run_cancellable so it shows the cancel button and can be interrupted.
        Updates self.current_file in-place if the processor returns a new path.
        """
        if not self.current_file:
            self._ui_warn("Advertencia", "Primero selecciona un archivo")
            return

        def process():
            self._raise_if_cancelled()
            try:
                self.update_status("Mejorando colores...", 50, "🎨")
                self.log_message("Aplicando mejoras de color...")
                self.log_message(f"Contraste: {self.contrast_var.get():.1f}  Saturación: {self.saturation_var.get():.1f}")
                self.log_message(f"Vibrance: {self.vibrance_var.get():.2f}  Nitidez: {self.sharpness_var.get():.2f}  Temperatura: {self.temperature_var.get():+.2f}")

                enhanced_path = self.processor.enhance_colors(
                    self.current_file,
                    self.contrast_var.get(),
                    self.saturation_var.get(),
                    vibrance=self.vibrance_var.get(),
                    sharpness=self.sharpness_var.get(),
                    temperature=self.temperature_var.get(),
                )

                if enhanced_path != self.current_file:
                    self.current_file = enhanced_path
                    # Refresh the file-info panel on the main thread via update_queue.
                    def update_ui():
                        self.show_file_info()
                    self.update_queue.put((update_ui, ()))

                    self.update_status("¡Colores mejorados!", 100, "✅")
                    self.log_message(f"Archivo mejorado: {enhanced_path.name}", "SUCCESS")

                    self._ui_info("¡Éxito!", 
                        f"¡Colores mejorados exitosamente!\n\n" +
                        f"📁 Archivo: {enhanced_path.name}\n" +
                        f"🎨 Contraste: {self.contrast_var.get():.1f}\n" +
                        f"🎨 Saturación: {self.saturation_var.get():.1f}")

            except Exception as e:
                self.update_status("Error", 0, "❌")
                self.log_message(f"ERROR: {e}", "ERROR")
                self._ui_error("Error", f"Error: {e}")

        self._run_cancellable(process)


    def convert_mp4_to_gif(self):
        """Open a configuration dialog for MP4-to-GIF conversion, then run it via _run_cancellable.

        The dialog collects fps, quality preset, resize, and color-enhance options before
        spawning the worker thread. Size estimates are recalculated live as the user adjusts sliders.
        """
        if not self.current_file:
            self._ui_warn("Advertencia", "Primero selecciona un archivo")
            return

        # Verificar que sea un video
        if not self.current_file.suffix.lower() in ['.mp4', '.avi', '.mov', '.mkv', '.webm']:
            self._ui_warn("Advertencia", 
                "El archivo seleccionado no es un video.\n" +
                "Formatos soportados: MP4, AVI, MOV, MKV, WEBM")
            return

        # Ventana de configuración
        config_window = ctk.CTkToplevel(self.root)
        config_window.title("Convertir Video a GIF")
        config_window.geometry("480x520")
        config_window.transient(self.root)
        config_window.grab_set()

        # Título
        ctk.CTkLabel(config_window, text="Conversion Video a GIF",
                     font=Fonts.HEADING,
                     text_color=Colors.ACCENT).pack(pady=(20, 10))

        # Frame principal scrollable
        main_frame = ctk.CTkScrollableFrame(config_window, fg_color="transparent")
        main_frame.pack(fill="both", expand=True, padx=20, pady=10)

        # Información del archivo
        ctk.CTkLabel(main_frame, text="Archivo seleccionado",
                     font=("Segoe UI", 10, "bold"),
                     text_color=Colors.TEXT).pack(anchor="w", pady=(0, 5))

        ctk.CTkLabel(main_frame, text=f"Archivo: {self.current_file.name}",
                     font=Fonts.CAPTION, text_color=Colors.TEXT_SECONDARY).pack(anchor="w")

        # Obtener info del video
        try:
            VideoFileClip = self._lazy_moviepy()
            with VideoFileClip(str(self.current_file)) as clip:
                duration = clip.duration
                fps_original = clip.fps
                size_original = f"{clip.w}x{clip.h}"

            ctk.CTkLabel(main_frame, text=f"Duracion: {duration:.1f}s | FPS: {fps_original:.1f} | {size_original}",
                         font=Fonts.CAPTION, text_color=Colors.TEXT_SECONDARY).pack(anchor="w")
        except Exception as e:
            ctk.CTkLabel(main_frame, text="No se pudo leer info del video",
                         text_color=Colors.WARNING).pack(anchor="w")
            duration = 10
            fps_original = 24

        # Configuración FPS
        ctk.CTkLabel(main_frame, text="FPS para el GIF",
                     font=("Segoe UI", 10, "bold"),
                     text_color=Colors.TEXT).pack(anchor="w", pady=(15, 5))

        fps_var = tk.IntVar(value=min(24, int(fps_original)))

        fps_options_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        fps_options_frame.pack(fill="x", pady=(0, 5))

        for fps_option in [12, 15, 20, 24, 30]:
            ctk.CTkRadioButton(fps_options_frame, text=f"{fps_option}",
                               variable=fps_var, value=fps_option,
                               font=Fonts.SMALL, radiobutton_width=16,
                               radiobutton_height=16).pack(side="left", padx=(0, 10))

        # FPS personalizado
        custom_var = tk.BooleanVar()
        custom_fps_var = tk.IntVar(value=24)

        custom_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        custom_frame.pack(fill="x", pady=(5, 0))

        ctk.CTkCheckBox(custom_frame, text="FPS personalizado:",
                        variable=custom_var, font=Fonts.SMALL,
                        checkbox_width=18, checkbox_height=18).pack(side="left")
        ctk.CTkEntry(custom_frame, textvariable=custom_fps_var, width=60,
                     height=28).pack(side="left", padx=(10, 0))

        # Configuración de calidad
        ctk.CTkLabel(main_frame, text="Calidad",
                     font=("Segoe UI", 10, "bold"),
                     text_color=Colors.TEXT).pack(anchor="w", pady=(15, 5))

        quality_var = tk.StringVar(value="balanced")

        for val, label in [("fast", "Rapido"), ("balanced", "Balanceado"), ("high", "Alta calidad")]:
            ctk.CTkRadioButton(main_frame, text=label,
                               variable=quality_var, value=val,
                               font=Fonts.SMALL, radiobutton_width=16,
                               radiobutton_height=16).pack(anchor="w", pady=2)

        # Opciones adicionales
        ctk.CTkLabel(main_frame, text="Opciones",
                     font=("Segoe UI", 10, "bold"),
                     text_color=Colors.TEXT).pack(anchor="w", pady=(15, 5))

        resize_var = tk.BooleanVar(value=True)
        enhance_var = tk.BooleanVar(value=False)

        ctk.CTkCheckBox(main_frame, text="Redimensionar a 638x354 (Steam)",
                        variable=resize_var, font=Fonts.SMALL,
                        checkbox_width=18, checkbox_height=18).pack(anchor="w", pady=2)
        ctk.CTkCheckBox(main_frame, text="Mejorar colores automaticamente",
                        variable=enhance_var, font=Fonts.SMALL,
                        checkbox_width=18, checkbox_height=18).pack(anchor="w", pady=2)

        # Estimación de tamaño
        estimate_label = ctk.CTkLabel(main_frame, text="Tamano estimado: Calculando...",
                                      font=Fonts.CAPTION, text_color=Colors.TEXT_MUTED)
        estimate_label.pack(anchor="w", pady=(10, 0))

        def update_estimate():
            try:
                fps = custom_fps_var.get() if custom_var.get() else fps_var.get()
                fps = max(1, min(60, fps))
                # Rough heuristic: ~0.02 MB per frame at 638x354 before quality adjustments.
                base_size = duration * fps * 0.02

                if quality_var.get() == "fast":
                    base_size *= 0.7
                elif quality_var.get() == "high":
                    base_size *= 1.4

                if resize_var.get():
                    base_size *= 0.8

                estimate_label.configure(text=f"Tamano estimado: ~{base_size:.1f} MB")
            except Exception:
                estimate_label.configure(text="Tamano estimado: No disponible")

        # Recompute the size estimate whenever any relevant variable changes.
        fps_var.trace_add("write", lambda *args: update_estimate())
        custom_fps_var.trace_add("write", lambda *args: update_estimate())
        quality_var.trace_add("write", lambda *args: update_estimate())
        resize_var.trace_add("write", lambda *args: update_estimate())
        custom_var.trace_add("write", lambda *args: update_estimate())

        update_estimate()  # populate initial estimate before the user changes anything

        # Botones
        button_frame = ctk.CTkFrame(config_window, fg_color="transparent")
        button_frame.pack(fill="x", padx=20, pady=15)

        def start_conversion():
            # Close the config dialog immediately so the user sees the progress bar.
            config_window.destroy()

            fps = custom_fps_var.get() if custom_var.get() else fps_var.get()
            fps = max(1, min(60, fps))
            quality = quality_var.get()
            should_resize = resize_var.get()
            should_enhance = enhance_var.get()

            def process():
                self._raise_if_cancelled()
                source_file = self.current_file  # keep for the manifest; current_file is reassigned below
                try:
                    self.update_status("Convirtiendo video a GIF...", 20, "🎬")
                    self.log_message("=== CONVERSIÓN MP4 → GIF ===", "INFO")
                    self.log_message(f"Archivo: {self.current_file.name}")
                    self.log_message(f"FPS: {fps}")
                    self.log_message(f"Calidad: {quality}")
                    self.log_message(f"Redimensionar: {should_resize}")

                    # Output goes into a dedicated workspace subdirectory to keep things tidy.
                    _conv_dir = self.processor._workspace_dir(self.current_file, "convertido")
                    _conv_name = f"{self.current_file.stem}.gif"
                    # Archive any existing output with the same name to avoid silent overwrites.
                    self.processor._archive_before_overwrite(_conv_dir, keep_names=[_conv_name, f"{self.current_file.stem}_converted.gif"])
                    output_path = _conv_dir / _conv_name

                    # Convertir usando el procesador
                    result = self.processor.convert_video_to_gif(
                        self.current_file, output_path, fps
                    )

                    if result:
                        self.update_status("Conversión completada", 80, "✅")

                        # Aplicar mejoras opcionales
                        final_result = result

                        if should_enhance:
                            self.update_status("Mejorando colores...", 85, "🎨")
                            self.log_message("Aplicando mejoras de color...")
                            enhanced = self.processor.enhance_colors(result, 1.2, 1.1)
                            if enhanced != result:
                                final_result = enhanced

                    # Actualizar archivo actual
                        self.current_file = final_result

                        def update_ui():
                            self.show_file_info()

                        self.update_queue.put((update_ui, ()))

                        # Mostrar estadísticas
                        final_size = final_result.stat().st_size / (1024 * 1024)

                        self.update_status("¡Conversión completada!", 100, "✅")
                        self.log_message(f"GIF creado: {final_result.name}", "SUCCESS")
                        self.log_message(f"Tamaño final: {final_size:.2f} MB", "SUCCESS")

                        try:
                            self.processor._write_manifest(_conv_dir, "convertir_video_a_gif",
                                {"fps": fps, "mejorar_colores": bool(should_enhance)},
                                archivos=[final_result], fuente=source_file)
                        except Exception:
                            pass

                        self._ui_info("¡Conversión Exitosa!", 
                            f"🎉 ¡Video convertido a GIF!\n\n" +
                            f"📁 Archivo: {final_result.name}\n" +
                            f"⚡ FPS: {fps}\n" +
                            f"📊 Tamaño: {final_size:.2f} MB\n" +
                            f"🎨 Mejoras: {'Sí' if should_enhance else 'No'}\n\n" +
                            f"✅ Listo para procesar con IA o fragmentar")

                    else:
                        raise Exception("No se pudo convertir el video")

                except Exception as e:
                    self.update_status("Error en conversión", 0, "❌")
                    self.log_message(f"ERROR: {e}", "ERROR")
                    self._ui_error("Error", f"Error convirtiendo video:\n\n{e}")

            self._run_cancellable(process)

        ctk.CTkButton(button_frame, text="Convertir a GIF",
                      command=start_conversion,
                      fg_color=Colors.ACCENT,
                      hover_color=Colors.ACCENT_DARK,
                      height=34, corner_radius=8).pack(side="right", padx=(10, 0))

        ctk.CTkButton(button_frame, text="Cancelar",
                      command=config_window.destroy,
                      fg_color="transparent", border_width=1,
                      border_color=Colors.BORDER,
                      hover_color=Colors.HOVER,
                      height=34, corner_radius=8).pack(side="right")
    def _open_fragment_preview(self):
        """Open the Steam profile simulator popup. Only reachable when PREVIEW_AVAILABLE is True."""
        if not self.current_file:
            self._ui_warn("Sin archivo", "Selecciona un archivo antes de abrir el preview.")
            return
        try:
            self.fragment_previewer.create_fragment_preview(self.current_file, self.root)
        except Exception as e:
            self._ui_error("Error", f"No se pudo abrir el preview:\n{e}")

    def enhance_animation(self):
        """Stub: RIFE frame-interpolation enhancement — replaced by the PRO patch at module load."""
        messagebox.showinfo(
            "WorkshopArt PRO",
            "La mejora de animacion con RIFE IA es una funcion exclusiva de la version PRO.\n\n"
            "Descarga el .exe compilado en:\n"
            "https://mxteoo7.itch.io/workshopart-pro\n\n"
            "La version gratuita incluye conversion MP4-a-GIF, mejora de colores,\n"
            "fragmentacion para todos los presets de Steam y procesamiento IA."
        )

    def _show_optimization_dialog(self, fragments_info, min_size, max_size):
        """Ask the user whether to apply automatic optimisation to out-of-range fragments.

        Returns False immediately (no dialog) if all fragments are already within [min_size, max_size].
        """
        small_count = sum(1 for f in fragments_info if f["size"] < min_size)
        large_count = sum(1 for f in fragments_info if f["size"] > max_size)

        if small_count == 0 and large_count == 0:
            return False  # all fragments are in range — skip the dialog

        dialog_text = f"🔧 OPTIMIZACIÓN NECESARIA\n\n"
        dialog_text += f"• Fragmentos pequeños: {small_count}/5\n"
        dialog_text += f"• Fragmentos grandes: {large_count}/5\n\n"

        if small_count > 0:
            dialog_text += f"Los fragmentos pequeños pueden ser rechazados por Steam.\n"
            dialog_text += f"La optimización aprovechará mejor el espacio disponible.\n\n"

        dialog_text += f"¿Aplicar optimización automática?\n\n"
        dialog_text += f"✅ SÍ: Mejora la calidad automáticamente\n"
        dialog_text += f"⚠️ NO: Mantiene fragmentos como están"

        return messagebox.askyesno("🔧 Optimización Recomendada", dialog_text)


    def _optimize_fragment_quality(self, fragment_path, target_size_mb, max_size_mb):
        """Increase a fragment's file size to be closer to target_size_mb without exceeding max_size_mb.

        Strategy 1: FFmpeg palettegen/paletteuse with escalating quality settings.
        Strategy 2: PIL frame-by-frame re-palette with adaptive colour count.
        Uses a temp file and only replaces the original on success.
        """
        try:
            current_size_mb = fragment_path.stat().st_size / (1024 * 1024)

            if current_size_mb >= target_size_mb:
                return True  # already at or above the target — nothing to do

            self.log_message(f"   Tamaño actual: {current_size_mb:.2f} MB, objetivo: {target_size_mb:.2f} MB")

            # Strategy 1: FFmpeg — faster and more reliable for most GIFs.
            success = self._optimize_with_ffmpeg_robust(fragment_path, target_size_mb, max_size_mb)
            if success:
                return True

            # Strategy 2: PIL frame-by-frame — fallback when FFmpeg is unavailable or fails.
            try:
                # Verificar que el archivo existe y es válido
                if not fragment_path.exists():
                    self.log_message(f"   Error: archivo no existe")
                    return False

                # Intentar abrir el GIF con múltiples métodos
                frames = []
                durations = []

                # ImageSequence.Iterator is safer than seek() for multi-frame GIFs.
                try:
                    with Image.open(fragment_path) as img:
                        # Verificar que es un GIF válido
                        if img.format != 'GIF':
                            self.log_message(f"   Error: no es un GIF válido")
                            return False

                        # Verificar que tiene frames
                        frame_count = getattr(img, 'n_frames', 0)
                        if frame_count == 0:
                            self.log_message(f"   Error: GIF sin frames")
                            return False

                        self.log_message(f"   GIF válido con {frame_count} frames")

                        # Extraer frames usando ImageSequence (más seguro)
                        for i, frame in enumerate(ImageSequence.Iterator(img)):
                            try:
                                # Copiar el frame para evitar problemas de referencia
                                frame_copy = frame.copy()

                                # Convertir a RGBA para consistencia
                                if frame_copy.mode != 'RGBA':
                                    frame_copy = frame_copy.convert('RGBA')

                                frames.append(frame_copy)

                                # Obtener duración del frame
                                duration = img.info.get('duration', 100)
                                if isinstance(duration, (list, tuple)):
                                    # Si es una lista, usar el índice correspondiente
                                    if i < len(duration):
                                        durations.append(duration[i])
                                    else:
                                        durations.append(100)  # Fallback
                                else:
                                    durations.append(duration)

                            except Exception as frame_error:
                                self.log_message(f"   Error procesando frame {i}: {frame_error}")
                                # Usar el último frame válido como fallback
                                if frames:
                                    frames.append(frames[-1].copy())
                                    durations.append(durations[-1] if durations else 100)

                        if not frames:
                            self.log_message(f"   Error: no se pudieron extraer frames")
                            return False

                        self.log_message(f"   Extraídos {len(frames)} frames exitosamente")

                except Exception as extraction_error:
                    self.log_message(f"   Error extrayendo frames: {extraction_error}")
                    return False

                # Map size ratio to colour depth: larger ratio → more colours → bigger file.
                size_multiplier = target_size_mb / current_size_mb

                # Configuración más conservadora para evitar errores
                if size_multiplier > 3:
                    colors = 256
                    quality_mode = "máxima"
                elif size_multiplier > 2:
                    colors = 224
                    quality_mode = "alta"
                elif size_multiplier > 1.5:
                    colors = 192
                    quality_mode = "media-alta"
                else:
                    colors = max(128, int(128 * size_multiplier))
                    quality_mode = "mejorada"

                self.log_message(f"   Aplicando calidad {quality_mode} con {colors} colores")

                # Procesar frames con manejo robusto de errores
                enhanced_frames = []

                for i, frame in enumerate(frames):
                    try:
                        # Asegurar que el frame está en modo correcto
                        if frame.mode == 'RGBA':
                            # Convertir RGBA a RGB para GIF
                            # Crear fondo blanco para transparencias
                            rgb_frame = Image.new('RGB', frame.size, (255, 255, 255))
                            rgb_frame.paste(frame, mask=frame.split()[-1] if frame.mode == 'RGBA' else None)
                            frame = rgb_frame
                        elif frame.mode != 'RGB':
                            frame = frame.convert('RGB')

                        # Aplicar mejora de calidad con configuración segura
                        if colors >= 256:
                            # Máxima calidad
                            frame_p = frame.convert('P', palette=Image.ADAPTIVE, colors=256)
                        else:
                            # Calidad configurada
                            frame_p = frame.convert('P', palette=Image.ADAPTIVE, colors=colors)

                        enhanced_frames.append(frame_p)

                    except Exception as process_error:
                        self.log_message(f"   Error procesando frame {i}: {process_error}")
                        # Usar frame anterior como fallback
                        if enhanced_frames:
                            enhanced_frames.append(enhanced_frames[-1].copy())
                        else:
                            # Si es el primer frame, crear uno básico
                            basic_frame = frame.convert('RGB').convert('P', colors=64)
                            enhanced_frames.append(basic_frame)

                if not enhanced_frames:
                    self.log_message(f"   Error: no se procesaron frames")
                    return False

                self.log_message(f"   Procesados {len(enhanced_frames)} frames")

                # Write to a temp file first; atomically replace original only on success.
                temp_path = fragment_path.with_suffix('.tmp.gif')

                try:
                    # Usar duración promedio para evitar problemas
                    if durations:
                        avg_duration = sum(durations) / len(durations)
                        # Asegurar duración mínima y máxima razonable
                        avg_duration = max(50, min(500, int(avg_duration)))
                    else:
                        avg_duration = 100

                    self.log_message(f"   Guardando con duración {avg_duration}ms")

                    # Guardar con configuración conservadora
                    enhanced_frames[0].save(
                        temp_path,
                        save_all=True,
                        append_images=enhanced_frames[1:] if len(enhanced_frames) > 1 else [],
                        duration=avg_duration,
                        loop=0,
                        optimize=False,  # No optimizar para mantener calidad
                        disposal=2  # Limpiar frame anterior
                    )

                    # Verificar que se creó correctamente
                    if not temp_path.exists():
                        self.log_message(f"   Error: no se creó archivo temporal")
                        return False

                    # Verificar tamaño
                    new_size_mb = temp_path.stat().st_size / (1024 * 1024)
                    self.log_message(f"   Resultado PIL: {new_size_mb:.2f} MB")

                    # Validar resultado
                    if target_size_mb <= new_size_mb <= max_size_mb:
                        # ¡Éxito! Reemplazar archivo original
                        shutil.move(temp_path, fragment_path)
                        self.log_message(f"   ✅ Optimizado con PIL: {current_size_mb:.2f} → {new_size_mb:.2f} MB")
                        return True

                    elif new_size_mb > current_size_mb and new_size_mb < max_size_mb:
                        # Mejora parcial - aceptable si no hay otras opciones
                        improvement = new_size_mb - current_size_mb
                        if improvement > 0.1:  # Al menos 0.1 MB de mejora
                            shutil.move(temp_path, fragment_path)
                            self.log_message(f"   ✅ Mejora parcial: {current_size_mb:.2f} → {new_size_mb:.2f} MB")
                            return True
                        else:
                            temp_path.unlink()
                            self.log_message(f"   Mejora insuficiente: +{improvement:.2f} MB")
                            return False
                    else:
                        # No cumple objetivos
                        temp_path.unlink()
                        if new_size_mb < target_size_mb:
                            self.log_message(f"   No alcanzó objetivo: {new_size_mb:.2f} < {target_size_mb:.2f}")
                        else:
                            self.log_message(f"   Excedió límite: {new_size_mb:.2f} > {max_size_mb:.2f}")
                        return False

                except Exception as save_error:
                    self.log_message(f"   Error guardando: {save_error}")
                    if temp_path.exists():
                        temp_path.unlink()
                    return False

            except Exception as pil_error:
                self.log_message(f"   Error general PIL: {pil_error}")
                return False

        except Exception as e:
            self.log_message(f"   Error crítico optimizando: {e}")
            return False

    def _optimize_with_ffmpeg_robust(self, fragment_path, target_size_mb, max_size_mb):
        """Try multiple palettegen/paletteuse FFmpeg strategies to hit the target size range.

        Strategies are scaled to the required size ratio: higher ratio needs more colours and
        higher dithering quality. Tries each in order; keeps the best partial result if none
        hits the exact target.
        """
        try:
            if not self.processor.check_ffmpeg():
                self.log_message(f"   FFmpeg no disponible")
                return False

            current_size_mb = fragment_path.stat().st_size / (1024 * 1024)
            size_multiplier = target_size_mb / current_size_mb

            strategies = []

            if size_multiplier > 4:
                # Necesitamos mucho más tamaño
                strategies = [
                    # Estrategia 1: Máxima calidad sin compresión
                    "split[s0][s1];[s0]palettegen=max_colors=256:stats_mode=single:reserve_transparent=0[p];[s1][p]paletteuse=dither=none",
                    # Estrategia 2: Calidad alta con dithering mínimo
                    "split[s0][s1];[s0]palettegen=max_colors=256:stats_mode=diff[p];[s1][p]paletteuse=dither=bayer:bayer_scale=1",
                    # Estrategia 3: Forzar más frames
                    "fps=32,split[s0][s1];[s0]palettegen=max_colors=256[p];[s1][p]paletteuse=dither=floyd_steinberg"
                ]
            elif size_multiplier > 2:
                # Incremento medio-alto
                strategies = [
                    # Estrategia 1: Buena calidad
                    "split[s0][s1];[s0]palettegen=max_colors=224:stats_mode=diff[p];[s1][p]paletteuse=dither=bayer:bayer_scale=2",
                    # Estrategia 2: Alternativa con 256 colores
                    "split[s0][s1];[s0]palettegen=max_colors=256:stats_mode=single[p];[s1][p]paletteuse=dither=sierra2"
                ]
            else:
                # Incremento moderado
                strategies = [
                    # Estrategia 1: Calidad mejorada balanceada
                    "split[s0][s1];[s0]palettegen=max_colors=192:stats_mode=diff[p];[s1][p]paletteuse=dither=floyd_steinberg",
                    # Estrategia 2: Más colores pero con dithering
                    "split[s0][s1];[s0]palettegen=max_colors=256[p];[s1][p]paletteuse=dither=bayer:bayer_scale=3"
                ]

            self.log_message(f"   Probando {len(strategies)} estrategias FFmpeg...")

            best_result = None
            best_size = current_size_mb

            for i, strategy in enumerate(strategies):
                temp_path = fragment_path.with_suffix(f'.ffmpeg_tmp_{i}.gif')

                try:
                    cmd = [
                        "ffmpeg",
                        "-i", str(fragment_path),
                        "-vf", strategy,
                        "-avoid_negative_ts", "make_zero",  # Evitar problemas de timestamp
                        "-y", str(temp_path)
                    ]

                    # Ejecutar con timeout más largo para fragmentos
                    result = subprocess.run(
                        cmd, 
                        capture_output=True, 
                        text=True, 
                        timeout=60,  # 1 minuto max por estrategia
                        cwd=fragment_path.parent,  # Ejecutar en el directorio correcto
                        **_NO_WINDOW_FLAGS
                    )

                    if result.returncode == 0 and temp_path.exists():
                        new_size_mb = temp_path.stat().st_size / (1024 * 1024)
                        self.log_message(f"   Estrategia FFmpeg {i+1}: {new_size_mb:.2f} MB")

                        # Verificar si cumple objetivo exacto
                        if target_size_mb <= new_size_mb <= max_size_mb:
                            # ¡Perfecto!
                            shutil.move(temp_path, fragment_path)
                            self.log_message(f"   ✅ FFmpeg estrategia {i+1} ÉXITO: {current_size_mb:.2f} → {new_size_mb:.2f} MB")

                            # Limpiar otros archivos temporales
                            self._cleanup_temp_files(fragment_path, i)
                            return True

                        # Verificar si es mejor que el anterior
                        elif new_size_mb > best_size and new_size_mb <= max_size_mb:
                            # Guardar como mejor opción por ahora
                            if best_result:
                                best_result.unlink()  # Eliminar resultado anterior
                            best_result = temp_path
                            best_size = new_size_mb
                            self.log_message(f"   Mejor resultado hasta ahora: {new_size_mb:.2f} MB")
                        else:
                            # No es útil
                            temp_path.unlink()
                    else:
                        # Error en ffmpeg
                        if temp_path.exists():
                            temp_path.unlink()

                        # Log del error sin spam
                        if result.stderr and "Error" in result.stderr:
                            error_summary = result.stderr.split('\n')[0][:100]
                            self.log_message(f"   Estrategia {i+1} error: {error_summary}")

                except subprocess.TimeoutExpired:
                    self.log_message(f"   Estrategia {i+1} timeout (>60s)")
                    if temp_path.exists():
                        temp_path.unlink()
                except Exception as e:
                    self.log_message(f"   Error estrategia {i+1}: {str(e)[:50]}")
                    if temp_path.exists():
                        temp_path.unlink()

            # Si tenemos un mejor resultado, usarlo
            if best_result and best_result.exists() and best_size > current_size_mb:
                improvement = best_size - current_size_mb
                if improvement >= 0.05:  # Al menos 50KB de mejora
                    shutil.move(best_result, fragment_path)
                    self.log_message(f"   ✅ FFmpeg mejor resultado: {current_size_mb:.2f} → {best_size:.2f} MB (+{improvement:.2f})")
                    return True
                else:
                    best_result.unlink()
                    self.log_message(f"   Mejora FFmpeg insuficiente: +{improvement:.2f} MB")

            self.log_message(f"   FFmpeg: ninguna estrategia alcanzó objetivo")
            return False

        except Exception as e:
            self.log_message(f"   Error general FFmpeg: {e}")
            return False

    def _optimize_with_ffmpeg(self, fragment_path, target_size_mb, max_size_mb):
        """Compatibility shim — delegates to _optimize_with_ffmpeg_robust."""
        return self._optimize_with_ffmpeg_robust(fragment_path, target_size_mb, max_size_mb)


    def _cleanup_temp_files(self, fragment_path, exclude_index=None):
        """Delete leftover ffmpeg_tmp_N and .tmp*.gif files after optimisation completes.

        exclude_index keeps the successful result file alive while cleaning up the others.
        """
        try:
            parent_dir = fragment_path.parent
            base_name = fragment_path.stem

            temp_patterns = [
                f"{base_name}.ffmpeg_tmp_*.gif",
                f"{base_name}.tmp*.gif"
            ]

            for pattern in temp_patterns:
                for temp_file in parent_dir.glob(pattern):
                    # Don't delete the file we just committed as the successful result.
                    if exclude_index is not None and f"tmp_{exclude_index}" in temp_file.name:
                        continue
                    try:
                        temp_file.unlink()
                    except Exception:
                        pass
        except Exception:
            pass

    def _show_final_fragments_report(self, source_file, min_size, max_size):
        """Collect fragment metadata then hand off to the enriched dialog on the main thread.

        source_file is the processed GIF; fragments are located in <stem>_workshop/fragmentos/.
        Uses root.after(0) to ensure the dialog is created on the main thread.
        """
        fragments_info = []
        total_size = 0

        fragments = self.processor.list_fragments(source_file, "_part_")
        for idx, frag in enumerate(fragments, 1):
            size_mb = frag.stat().st_size / (1024 * 1024)
            fragments_info.append({
                "part": idx,
                "path": frag,
                "size": size_mb
            })
            total_size += size_mb

        # Schedule the dialog on the main thread (this method may be called from a worker thread).
        self.root.after(0, lambda: self._show_fragments_dialog(fragments_info, total_size, min_size, max_size))

    # JavaScript to paste into the browser console on the Steam Workshop upload page.
    # Sets the app to "Spacewar" (480) so any account can upload, file_type=0 for artwork,
    # and visibility=0 for public. Shared between the help text and the copy button.
    STEAM_JS_SNIPPET = (
        "$J('[name=consumer_app_id]').val(480);\n"
        "$J('[name=file_type]').val(0);\n"
        "$J('[name=visibility]').val(0);"
    )

    def _copy_steam_js(self):
        """Copiar snippet JS de Steam al portapapeles."""
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(self.STEAM_JS_SNIPPET)
            self.root.update()
            self.log_message("Snippet JS copiado al portapapeles", "SUCCESS")
            self._ui_info("Copiado", "Snippet JS copiado al portapapeles.\nPégalo en la consola del navegador (F12).")
        except Exception as e:
            self._ui_error("Error", f"No se pudo copiar: {e}")

    def _build_grid_preview(self, fragments_info, target_width=720):
        """Composite the 5 fragment images into a single preview mimicking the Steam showcase layout.

        Uses 4 px gaps to match Steam's actual rendering. Scales down to target_width so the
        preview fits inside the dialog without scrolling.
        """
        if not fragments_info:
            return None
        # Steam Workshop showcase layout: 5 × 638×354, 4 px gaps between slots.
        FRAG_W, FRAG_H, GAP = 638, 354, 4
        total_w = FRAG_W * 5 + GAP * 4
        # Escalar al ancho objetivo
        scale = target_width / total_w
        sw, sh, sg = int(FRAG_W * scale), int(FRAG_H * scale), max(1, int(GAP * scale))
        canvas_w = sw * 5 + sg * 4
        canvas = Image.new('RGBA', (canvas_w, sh), (20, 20, 25, 255))
        for idx, info in enumerate(sorted(fragments_info, key=lambda f: f['part'])):
            if idx >= 5:
                break
            try:
                with Image.open(info['path']) as img:
                    frame = img.convert('RGBA')
                    frame.thumbnail((sw, sh), Image.Resampling.LANCZOS)
                x = idx * (sw + sg)
                canvas.paste(frame, (x, 0))
            except Exception as e:
                self.log_message(f"Error en preview del fragment {info['part']}: {e}", "WARNING")
        return canvas

    def _show_fragments_dialog(self, fragments_info, total_size, min_size, max_size):
        """Display the post-fragmentation dialog with a grid preview, file list, and upload actions.

        Must run on the main thread. Each fragment row has a checkbox so the user can select
        which parts to auto-upload via _auto_upload_selected.
        """
        optimal_count = sum(1 for f in fragments_info if min_size <= f["size"] <= max_size)
        small_count = sum(1 for f in fragments_info if f["size"] < min_size)
        large_count = sum(1 for f in fragments_info if f["size"] > max_size)

        win = ctk.CTkToplevel(self.root)
        win.title("🎉 Fragmentación Completada")
        win.geometry("820x680")
        win.transient(self.root)
        try:
            win.grab_set()
        except Exception:
            pass

        # Título
        ctk.CTkLabel(win, text="🎉 Fragmentación Completada",
                     font=Fonts.TITLE).pack(pady=(16, 4))
        ctk.CTkLabel(win,
                     text=f"✅ {optimal_count}/5 óptimos   ⚠️ {small_count} pequeños   ❌ {large_count} grandes   📊 {total_size:.2f} MB total",
                     font=Fonts.BODY).pack(pady=(0, 10))

        # Grid preview
        preview_frame = ctk.CTkFrame(win, fg_color="transparent")
        preview_frame.pack(pady=(0, 10), padx=16, fill="x")
        ctk.CTkLabel(preview_frame, text="Preview del showcase (gap 4px como en Steam):",
                     font=Fonts.SMALL).pack(anchor="w")
        try:
            grid_img = self._build_grid_preview(fragments_info, target_width=770)
            if grid_img is not None:
                self._grid_preview_photo = ImageTk.PhotoImage(grid_img)
                ctk.CTkLabel(preview_frame, image=self._grid_preview_photo, text="").pack(pady=4)
                grid_img.close()
        except Exception as e:
            ctk.CTkLabel(preview_frame, text=f"(Preview no disponible: {e})").pack()

        # Lista de archivos (scrollable)
        list_frame = ctk.CTkScrollableFrame(win, height=140)
        list_frame.pack(fill="x", padx=16, pady=(0, 10))
        self._fragment_checkboxes = {}
        for info in fragments_info:
            if min_size <= info['size'] <= max_size:
                status = "✅"
            elif info['size'] < min_size:
                status = "⚠️"
            else:
                status = "❌"
            row = ctk.CTkFrame(list_frame, fg_color="transparent")
            row.pack(fill="x", pady=2)
            var = tk.BooleanVar(value=True)
            self._fragment_checkboxes[info['part']] = (var, info)
            ctk.CTkCheckBox(row, text="", variable=var, width=24).pack(side="left", padx=(0, 6))
            ctk.CTkLabel(row, text=f"{status} Parte {info['part']}: {info['path'].name}  —  {info['size']:.2f} MB",
                         font=Fonts.BODY, anchor="w").pack(side="left", fill="x", expand=True)

        # Botones de acción
        btn_frame = ctk.CTkFrame(win, fg_color="transparent")
        btn_frame.pack(fill="x", padx=16, pady=(4, 12))

        if fragments_info:
            _folder = fragments_info[0]['path'].parent
            ctk.CTkButton(btn_frame, text="📁 Abrir carpeta",
                          command=lambda p=_folder: os.startfile(p),
                          fg_color=Colors.BG_TERTIARY, hover_color=Colors.HOVER,
                          height=36).pack(side="left", padx=4)

        ctk.CTkButton(btn_frame, text="📋 Copiar JS Steam",
                      command=self._copy_steam_js,
                      fg_color=Colors.ACCENT, hover_color=Colors.ACCENT_DARK,
                      height=36).pack(side="left", padx=4)

        ctk.CTkButton(btn_frame, text="🌐 Abrir Workshop",
                      command=lambda: webbrowser.open("https://steamcommunity.com/sharedfiles/edititem/767/3/"),
                      height=36).pack(side="left", padx=4)

        ctk.CTkButton(btn_frame, text="🚀 Auto-subir seleccionados",
                      command=lambda: self._auto_upload_selected(win),
                      fg_color="#16a34a", hover_color="#15803d",
                      height=36).pack(side="left", padx=4)

        ctk.CTkButton(btn_frame, text="Cerrar",
                      command=win.destroy, height=36).pack(side="right", padx=4)

    def _auto_upload_selected(self, parent_win):
        """Upload the checked fragments to Steam Workshop using the private steam_uploader module.

        steam_uploader.py and steam_cookies.json are gitignored (personal/PRO only). Shows an
        informative warning if the module or cookies are missing. Upload runs in a daemon thread
        with progress dispatched through update_queue.
        """
        # Lazy import: this is a private module not shipped in the public repo.
        try:
            import steam_uploader
        except ImportError:
            self._ui_warn(
                "Auto-upload no disponible",
                "El módulo privado 'steam_uploader' no está instalado.\n\n"
                "Para habilitarlo, coloca src/steam_uploader.py y steam_cookies.json "
                "(ambos gitignoreados)."
            )
            return

        if not steam_uploader.cookies_configured():
            self._ui_warn(
                "Cookies no disponibles",
                "El uploader necesita cookies de Steam. Opciones:\n\n"
                "1) Instala browser_cookie3 (pip install browser_cookie3) y loguéate en "
                "Steam desde Firefox. Cierra Firefox antes de subir.\n\n"
                "2) O crea 'steam_cookies.json' en la raíz con las claves "
                "sessionid y steamLoginSecure (F12 en steamcommunity.com → "
                "Application → Cookies)."
            )
            return
        src = steam_uploader.cookies_source()
        self.log_message(f"Fuente de cookies Steam: {src}", "INFO")

        selected = [info['path'] for part, (var, info) in self._fragment_checkboxes.items() if var.get()]
        if not selected:
            self._ui_warn("Nada que subir", "No has marcado ningún fragmento.")
            return

        if not messagebox.askyesno("Confirmar auto-upload",
                                   f"Se subirán {len(selected)} fragmentos a Steam Workshop.\n\n¿Continuar?"):
            return

        def worker():
            def progress(i, total, msg):
                # Dispatch both log and status updates via update_queue (worker -> main thread).
                self.update_queue.put((self.log_message, (f"[Upload {i}/{total}] {msg}", "INFO")))
                self.update_queue.put((self.update_status, (f"Subiendo {i}/{total}...", int(i*100/total), "🚀")))
            try:
                results = steam_uploader.upload_fragments(selected, progress_cb=progress)
                ok = sum(1 for _, b, _ in results if b)
                fail = len(results) - ok
                summary = f"Subidos: {ok}/{len(results)}\n\n"
                for path, good, msg in results:
                    summary += f"{'✅' if good else '❌'} {path.name}: {msg}\n"
                if fail == 0:
                    self._ui_info("Auto-upload completado", summary)
                else:
                    self._ui_error("Auto-upload con errores", summary)
            except Exception as e:
                self._ui_error("Error en auto-upload", str(e))

        threading.Thread(target=worker, daemon=True).start()

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
        self.log_message("WorkshopArt v1.0 iniciado", "SUCCESS")
        self.log_message("✨ Versión modular con todas las funciones", "INFO")
        self.log_message("📁 Selecciona un archivo para comenzar", "INFO")

        # Ejecutar loop principal
        self.root.mainloop()

    def optimize_to_steam_limit(self):
        """Optimise one or more GIFs to fit within the Steam Workshop 5 MB limit.

        Default target range is [94% of max_mb, max_mb] to maximise quality while staying
        under the limit. Single-file mode uses individual palette refinement; multi-file batch
        mode uses a shared FFmpeg strategy so all fragments stay visually synchronised.
        """
        # Pedir archivos al usuario
        initial = str(self.current_file.parent) if self.current_file else ""
        paths = filedialog.askopenfilenames(
            title="Selecciona fragmentos GIF a optimizar",
            initialdir=initial,
            filetypes=[("GIFs", "*.gif"), ("Todos", "*.*")],
        )
        if not paths:
            return
        files = [Path(p) for p in paths]

        # Pedir límite máximo (por defecto 5.0)
        from tkinter.simpledialog import askfloat
        max_mb = askfloat("Límite máximo",
                          "Tamaño máximo por fragmento (MB):\n"
                          "Steam Workshop rechaza > 5 MB.\n"
                          "Recomendado: 5.0",
                          initialvalue=5.0, minvalue=0.5, maxvalue=20.0)
        if max_mb is None:
            return
        # Target floor at 94% of max so the optimizer pushes quality as high as possible.
        min_mb = max(0.1, max_mb * 0.94)

        self.log_message(f"=== OPTIMIZACIÓN A ≤{max_mb:.2f} MB ({len(files)} archivos) ===", "INFO")

        def process():
            self._raise_if_cancelled()
            results: list[tuple[Path, Optional[Path], float, float]] = []
            try:
                originals = [(p, p.stat().st_size / (1024 * 1024)) for p in files]
                if len(files) > 1:
                    # Batch mode: shared FFmpeg strategy keeps all fragments visually in sync.
                    self.update_status(f"Optimizando {len(files)} fragmentos (batch)...",
                                       10, "🎯")
                    self.log_message(f"Modo batch: estrategia compartida para sincronización", "INFO")
                    outputs = self.processor.shrink_batch_to_size_cap(
                        files, max_mb=max_mb, min_mb=min_mb,
                        progress_cb=lambda m: self.log_message(f"   {m}")
                    )
                    for (p, omb), out in zip(originals, outputs):
                        fmb = out.stat().st_size / (1024 * 1024) if out and out.exists() else 0.0
                        results.append((p, out, omb, fmb))
                else:
                    # Single file: individual optimizer with per-file palette refinement.
                    for i, path in enumerate(files, 1):
                        self._raise_if_cancelled()
                        original_mb = originals[i - 1][1]
                        self.update_status(f"Optimizando {i}/{len(files)}: {path.name}",
                                           int(i * 100 / max(1, len(files))), "🎯")
                        self.log_message(f"[{i}/{len(files)}] {path.name} ({original_mb:.2f} MB)")
                        out = self.processor.shrink_to_size_cap(
                            path, max_mb=max_mb, min_mb=min_mb,
                            progress_cb=lambda m: self.log_message(f"   {m}")
                        )
                        final_mb = out.stat().st_size / (1024 * 1024) if out and out.exists() else 0.0
                        results.append((path, out, original_mb, final_mb))

                # Resumen
                ok = sum(1 for _, o, _, f in results if o is not None and f <= max_mb)
                self.update_status("Optimización terminada", 100, "✅")
                lines = [f"Archivos procesados: {len(results)}",
                         f"Dentro del límite ≤{max_mb:.1f} MB: {ok}/{len(results)}",
                         ""]
                for src_path, out_path, omb, fmb in results:
                    if out_path is None:
                        lines.append(f"❌ {src_path.name}: no se pudo optimizar")
                    else:
                        mark = "✅" if fmb <= max_mb else "⚠️"
                        lines.append(f"{mark} {src_path.name}: {omb:.2f} → {fmb:.2f} MB")
                        lines.append(f"   → {out_path.name}")
                summary = "\n".join(lines)
                if ok == len(results):
                    self._ui_info("Optimización completada", summary)
                else:
                    self._ui_warn("Optimización con avisos", summary)
            except InterruptedError:
                raise
            except Exception as e:
                self.log_message(f"Error en optimización: {e}", "ERROR")
                self._ui_error("Error", f"Error en optimización: {e}")

        self._run_cancellable(process)

    def fragment_for_steam(self):
        """Show the unified fragmentation dialog with all Steam format presets as radio buttons.

        Routes to _fragment_workshop_flow, fragment_for_artwork_direct, or
        fragment_for_showcase_preset depending on which preset the user selects.
        """
        if not self.current_file:
            self._ui_warn("Advertencia", "Primero selecciona un archivo")
            return

        dlg = ctk.CTkToplevel(self.root)
        dlg.title("Fragmentar para Steam")
        dlg.geometry("520x640")
        dlg.resizable(False, False)
        dlg.transient(self.root)
        dlg.grab_set()

        dlg.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - 520) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - 640) // 2
        dlg.geometry(f"+{x}+{y}")

        ctk.CTkLabel(dlg, text="Fragmentar para Steam",
                     font=("Segoe UI", 16, "bold")).pack(pady=(16, 2))
        ctk.CTkLabel(dlg, text=f"Archivo: {self.current_file.name}",
                     font=("Segoe UI", 10), text_color="#aaaaaa").pack(pady=(0, 8))

        var = ctk.StringVar(value="workshop_5part")

        scroll = ctk.CTkScrollableFrame(dlg, height=450)
        scroll.pack(fill="both", expand=True, padx=16, pady=(0, 6))

        def _section(text, color="#888888"):
            ctk.CTkLabel(scroll, text=text, font=("Segoe UI", 10, "bold"),
                         text_color=color).pack(anchor="w", padx=8, pady=(12, 3))
            ctk.CTkFrame(scroll, height=1, fg_color="#333333").pack(fill="x", padx=8, pady=(0, 4))

        def _opt(key, label, dims="", note="", badge=""):
            f = ctk.CTkFrame(scroll, fg_color="#1e2533", corner_radius=8)
            f.pack(fill="x", padx=4, pady=2)
            row = ctk.CTkFrame(f, fg_color="transparent")
            row.pack(fill="x", padx=10, pady=6)
            ctk.CTkRadioButton(row, text=label, variable=var, value=key,
                               font=("Segoe UI", 12, "bold")).pack(side="left", anchor="w")
            if badge:
                ctk.CTkLabel(row, text=badge, font=("Segoe UI", 8, "bold"),
                             text_color="#58a6ff",
                             fg_color="#0d2847", corner_radius=4,
                             padx=5, pady=1).pack(side="left", padx=(6, 0))
            if dims:
                ctk.CTkLabel(f, text=dims, font=("Segoe UI", 9),
                             text_color="#58a6ff").pack(anchor="w", padx=28, pady=(0, 2))
            if note:
                ctk.CTkLabel(f, text=note, font=("Segoe UI", 9),
                             text_color="#666").pack(anchor="w", padx=28, pady=(0, 5))

        # ── Workshop / Profile animated banner ───────────────────────────
        _section("WORKSHOP SHOWCASE — BANNER ANIMADO", "#c0392b")
        _opt("workshop_5part",
             "Workshop Showcase · 5 partes horizontales",
             "5 × 638 × 354 px  |  total: 3190 × 354",
             "Formato principal para GIFs animados en el perfil de Steam",
             badge="MAS USADO")

        # ── Artwork showcase ─────────────────────────────────────────────
        _section("ARTWORK SHOWCASE")
        _opt("artwork_2part",
             "Main + Side  (recomendado)",
             "506 px main + 100 px side  |  alto libre",
             "Diseño clásico de 2 columnas · acepta GIFs y estáticos")
        _opt("featured_630",
             "Featured Artwork · 1 slot destacado",
             "630 × H  |  alto libre",
             "Imagen/GIF grande en la parte superior del perfil")
        _opt("artwork_single_630",
             "Artwork Single · 16:9",
             "630 × 354 px  |  1 slot",
             "Un único GIF o imagen en proporción 16:9")
        _opt("artwork_4grid",
             "Artwork 4-grid · cuadrícula",
             "4 × 245 × 245 px  |  total: 980 × 245",
             "Cuatro cuadrados iguales formando un banner")
        _opt("panorama_5_630",
             "Panorama · banner ultra-ancho",
             "5 × 630 × 360 px  |  total: 3150 × 360",
             "Banner horizontal ancho de 5 piezas")

        # ── Screenshot showcase ──────────────────────────────────────────
        _section("SCREENSHOT SHOWCASE")
        _opt("screenshot_638",
             "Screenshot Simple · 1 slot",
             "638 × 354 px  |  file_type=5",
             "Una sola captura animada en el showcase de screenshots")
        _opt("screenshot_4grid",
             "Screenshot 4-grid · cuadrícula 2×2",
             "4 × 638 × 354 px  |  total: 2552 × 354",
             "Cuatro screenshots formando una tira horizontal")

        # ── Workshop grid (small squares) ────────────────────────────────
        _section("WORKSHOP SHOWCASE — CUADRADOS")
        _opt("workshop_5slot_150",
             "Workshop Grid · 5 × 150 px",
             "5 × 150 × 150 px  |  total: 750 × 150",
             "Tamaño de upload recomendado, sin bordes negros")
        _opt("workshop_5slot_119",
             "Workshop Grid · 5 × 119 px (nativo)",
             "5 × 119 × 119 px  |  total: 595 × 119",
             "Tamaño de display nativo de Steam Workshop")

        btns = ctk.CTkFrame(dlg, fg_color="transparent")
        btns.pack(fill="x", padx=16, pady=(0, 12))

        def _go():
            choice = var.get()
            dlg.destroy()
            if choice == "workshop_5part":
                self._fragment_workshop_flow()
            elif choice == "artwork_2part":
                self.fragment_for_artwork_direct()
            else:
                self.fragment_for_showcase_preset(choice)

        ctk.CTkButton(btns, text="Fragmentar", command=_go,
                      fg_color="#c0392b", hover_color="#962d22",
                      height=38, corner_radius=8,
                      font=("Segoe UI", 12, "bold")).pack(side="left", padx=(0, 8))
        ctk.CTkButton(btns, text="Cancelar", command=dlg.destroy,
                      fg_color="transparent", hover_color="#333333",
                      border_width=1, border_color="#555555",
                      height=38, corner_radius=8,
                      font=("Segoe UI", 11)).pack(side="left")

    def _fragment_workshop_flow(self):
        """Entry point for the workshop 5-part flow. Stub delegates to fragment_for_steam_direct;
        the PRO patch replaces this with a version that includes a before/after preview dialog."""
        self.fragment_for_steam_direct()

    def fragment_for_steam_direct(self):
        """Split the current file into 5 horizontal Workshop Showcase fragments without a preview step.

        Auto-converts video to GIF first if needed. Runs via _run_cancellable.
        Results are shown in _show_final_fragments_report.
        """
        if not self.current_file:
            self._ui_warn("Advertencia", "Primero selecciona un archivo")
            return

        def process():
            self._raise_if_cancelled()
            try:
                self.update_status("Iniciando fragmentación...", 10, "✂️")
                self.log_message("=== FRAGMENTACIÓN DIRECTA ===", "INFO")
                self.log_message(f"Archivo: {self.current_file.name}")

                # Auto-convert video formats to GIF before splitting.
                if self.current_file.suffix.lower() != '.gif':
                    self.log_message("Convirtiendo a GIF...")
                    self.update_status("Convirtiendo a GIF...", 20, "🎬")
                    gif_path = self.current_file.with_suffix('.gif')
                    gif_path = self.processor.convert_video_to_gif(self.current_file, gif_path)
                    if not gif_path:
                        raise Exception("Error convirtiendo a GIF")
                    self.current_file = gif_path

                # Fragmentar usando el procesador
                self.update_status("Fragmentando en 5 partes...", 50, "✂️")
                self.log_message("Fragmentando para Steam Workshop...")

                success = self.processor.split_gif_for_steam(self.current_file)

                if success:
                    self.update_status("¡Fragmentación completada!", 100, "✅")
                    self.log_message("Fragmentación completada exitosamente", "SUCCESS")

                    # list_fragments resolves paths inside the workspace, not the source dir.
                    fragments = self.processor.list_fragments(self.current_file, "_part_")
                    created_files = []
                    total_size = 0

                    for frag in fragments:
                        size_mb = frag.stat().st_size / (1024 * 1024)
                        created_files.append(f"✅ {frag.name}: {size_mb:.2f} MB")
                        total_size += size_mb
                        self.log_message(f"Creado: {frag.name} ({size_mb:.2f} MB)", "SUCCESS")

                    if not created_files:
                        raise Exception("No se encontraron fragmentos en el workspace tras la fragmentación")

                    frag_dir = self.processor.get_fragments_dir(self.current_file)
                    result_text = f"🎉 ¡Fragmentación completada!\n\n"
                    result_text += f"📁 Carpeta: {frag_dir}\n\n"
                    result_text += "\n".join(created_files)
                    result_text += f"\n\n📊 Tamaño total: {total_size:.2f} MB"
                    result_text += f"\n\n🎮 ¡Listos para subir a Steam Workshop!"

                    self._ui_info("¡Fragmentación Exitosa!", result_text)

                else:
                    raise Exception("La fragmentación falló")

            except Exception as e:
                self.update_status("Error en fragmentación", 0, "❌")
                self.log_message(f"ERROR: {e}", "ERROR")
                self._ui_error("Error", f"Error en fragmentación:\n\n{e}")
            finally:
                self.update_status("Listo", 0, "✅")

        # Ejecutar en thread separado
        self._run_cancellable(process)

    def fragment_for_artwork_direct(self):
        """Split the current file into the Artwork Showcase layout (506 px main + 100 px side panel).

        Supports both animated GIFs and static images. Runs via _run_cancellable.
        """
        if not self.current_file:
            self._ui_warn("Advertencia", "Primero selecciona un archivo")
            return

        def process():
            self._raise_if_cancelled()
            try:
                self.update_status("Iniciando fragmentación Artwork...", 10, "🎨")
                self.log_message("=== FRAGMENTACIÓN ARTWORK SHOWCASE ===", "INFO")
                self.log_message(f"Archivo: {self.current_file.name}")

                _is_static = self.current_file.suffix.lower() in _STATIC_IMAGE_EXTS

                if not _is_static and self.current_file.suffix.lower() != '.gif':
                    self.log_message("Convirtiendo a GIF...")
                    self.update_status("Convirtiendo a GIF...", 20, "🎬")
                    gif_path = self.current_file.with_suffix('.gif')
                    gif_path = self.processor.convert_video_to_gif(self.current_file, gif_path)
                    if not gif_path:
                        raise Exception("Error convirtiendo a GIF")
                    self.current_file = gif_path

                # Fragmentar usando el procesador
                self.update_status("Fragmentando en 2 paneles...", 50, "🎨")
                self.log_message("Fragmentando para Artwork Showcase (506 + 100 px)...")

                if _is_static:
                    success = self.processor.split_image_for_artwork_showcase(self.current_file)
                else:
                    success = self.processor.split_gif_for_artwork_showcase(self.current_file)

                if success:
                    self.update_status("¡Fragmentación Artwork completada!", 100, "✅")
                    self.log_message("Fragmentación Artwork completada exitosamente", "SUCCESS")

                    # Panels use "artwork_" prefix instead of "_part_" to distinguish them.
                    artwork_panels = self.processor.list_fragments(self.current_file, "artwork_")

                    if not artwork_panels:
                        raise Exception("No se encontraron paneles artwork en el workspace tras la fragmentación")

                    for frag in artwork_panels:
                        size_mb = frag.stat().st_size / (1024 * 1024)
                        self.log_message(f"Creado: {frag.name} ({size_mb:.2f} MB)", "SUCCESS")

                    self.root.after(0, lambda p=list(artwork_panels): self._show_artwork_result_dialog(p))

                else:
                    detail = getattr(self.processor, '_last_split_error', '') or ''
                    self.log_message(f"Error FFmpeg: {detail}", "ERROR")
                    raise Exception(f"La fragmentación Artwork falló.\n{detail}" if detail else "La fragmentación Artwork falló")

            except Exception as e:
                self.update_status("Error en fragmentación Artwork", 0, "❌")
                self.log_message(f"ERROR: {e}", "ERROR")
                self._ui_error("Error", f"Error en fragmentación Artwork:\n\n{e}")
            finally:
                self.update_status("Listo", 0, "✅")

        # Ejecutar en thread separado
        self._run_cancellable(process)

    def fragment_for_showcase_preset(self, preset: str = None):
        """Fragment the current file using a named showcase preset from SteamProcessor.SHOWCASE_PRESETS.

        If preset is None, opens a picker dialog first. Handles both static images and GIFs.
        """
        if not self.current_file:
            self._ui_warn("Advertencia", "Primero selecciona un archivo")
            return

        if preset is None:
            preset = self._pick_showcase_preset()
            if not preset:
                return

        proc = self.processor
        if preset not in proc.SHOWCASE_PRESETS:
            self._ui_error("Error", f"Preset desconocido: {preset}")
            return
        cfg = proc.SHOWCASE_PRESETS[preset]

        def process():
            self._raise_if_cancelled()
            try:
                self.update_status(f"Fragmentando '{preset}'...", 10, "🎨")
                self.log_message(f"=== SHOWCASE PRESET: {preset} ===", "INFO")
                self.log_message(f"Descripción: {cfg['desc']}")
                self.log_message(f"Archivo: {self.current_file.name}")

                _is_static = self.current_file.suffix.lower() in _STATIC_IMAGE_EXTS

                if not _is_static and self.current_file.suffix.lower() != '.gif':
                    self.update_status("Convirtiendo a GIF...", 20, "🎬")
                    gif_path = self.current_file.with_suffix('.gif')
                    gif_path = proc.convert_video_to_gif(self.current_file, gif_path)
                    if not gif_path:
                        raise Exception("Error convirtiendo a GIF")
                    self.current_file = gif_path

                self.update_status(f"Generando {len(cfg['parts'])} parte(s)...", 50, "✂️")
                if _is_static:
                    success = proc.split_image_for_showcase(self.current_file, preset)
                else:
                    success = proc.split_gif_for_showcase(self.current_file, preset)

                if not success:
                    raise Exception("Fragmentación falló")

                self.update_status("¡Completado!", 100, "✅")
                frag_dir = proc.get_fragments_dir(self.current_file)
                _img_exts = {'.gif', '.jpg', '.jpeg', '.png'}
                _stem = self.current_file.stem
                fragments = sorted(
                    p for p in Path(frag_dir).iterdir()
                    if p.is_file() and p.suffix.lower() in _img_exts and f"{_stem}_" in p.name
                )
                total_mb = sum(f.stat().st_size for f in fragments) / (1024 * 1024)
                for f in fragments:
                    mb = f.stat().st_size / (1024 * 1024)
                    self.log_message(f"Creado: {f.name} ({mb:.2f} MB)", "SUCCESS")
                self.root.after(0, lambda p=preset, c=cfg, fd=frag_dir,
                               fr=list(fragments), tm=total_mb:
                               self._show_showcase_result_dialog(p, c, fd, fr, tm))
            except Exception as e:
                self.update_status("Error", 0, "❌")
                self.log_message(f"ERROR: {e}", "ERROR")
                self._ui_error("Error", f"Error preset '{preset}':\n\n{e}")
            finally:
                self.update_status("Listo", 0, "✅")

        self._run_cancellable(process)

    def _show_showcase_result_dialog(self, preset: str, cfg: dict, frag_dir, fragments: list, total_mb: float):
        """Show the post-fragmentation result dialog with the correct upload JS snippet for the preset.

        spoof_dims=True (panorama preset) triggers dimension-spoofing JS so Steam accepts
        the ultra-wide image without rejecting it for aspect ratio.
        """
        upload_hint = cfg.get("upload_hint", "artwork")
        spoof = cfg.get("spoof_dims", False)

        # Per-format JS snippets: file_type and consumer_app_id differ by showcase type.
        _JS = {
            "artwork": (
                "$J('[name=consumer_app_id]').val(767);\n"
                "$J('[name=file_type]').val(3);\n"
                "$J('[name=visibility]').val(0);"
            ),
            "screenshot": (
                "$J('[name=consumer_app_id]').val(767);\n"
                "$J('[name=file_type]').val(5);\n"
                "$J('[name=visibility]').val(0);"
            ),
            "workshop": (
                "$J('[name=consumer_app_id]').val(480);\n"
                "$J('[name=file_type]').val(0);\n"
                "$J('[name=visibility]').val(0);"
            ),
            "panorama": (
                # Spoof image dimensions so Steam doesn't reject the wide aspect ratio.
                "$J('#image_width').val(1000).attr('id', '');\n"
                "$J('#image_height').val(1).attr('id', '');\n"
                "$J('[name=consumer_app_id]').val(767);\n"
                "$J('[name=file_type]').val(3);\n"
                "$J('[name=visibility]').val(0);"
            ),
        }
        js_code = _JS.get("panorama" if spoof else upload_hint, _JS["artwork"])

        root_win = self.root if hasattr(self, "root") else None
        dlg = ctk.CTkToplevel(root_win)
        dlg.title("Showcase listo")
        dlg.geometry("640x540")
        dlg.grab_set()

        ctk.CTkLabel(dlg, text=f"🎉 Preset '{preset}' completado",
                     font=("Segoe UI", 14, "bold")).pack(pady=(14, 2))
        ctk.CTkLabel(dlg, text=cfg["desc"],
                     text_color="#aaa", font=("Segoe UI", 11)).pack()
        ctk.CTkLabel(dlg,
                     text=f"Subir como: {upload_hint}  |  Total: {total_mb:.2f} MB  |  {len(fragments)} archivo(s)",
                     text_color="#888", font=("Segoe UI", 10)).pack(pady=(2, 8))

        flist = ctk.CTkScrollableFrame(dlg, height=110, label_text="Fragmentos generados")
        flist.pack(fill="x", padx=14, pady=(0, 8))
        for f in fragments:
            mb = f.stat().st_size / (1024 * 1024)
            ctk.CTkLabel(flist, text=f"✅  {f.name}   —   {mb:.2f} MB",
                         anchor="w", font=("Consolas", 10)).pack(anchor="w", padx=6, pady=1)

        ctk.CTkLabel(dlg, text="Consola del navegador (F12 → Console) — pega esto ANTES de guardar:",
                     font=("Segoe UI", 10, "bold"), anchor="w").pack(anchor="w", padx=14)
        js_box = ctk.CTkTextbox(dlg, height=85, font=("Consolas", 10))
        js_box.pack(fill="x", padx=14, pady=(2, 4))
        js_box.insert("end", js_code)
        js_box.configure(state="disabled")

        if preset == "artwork_2part":
            ctk.CTkLabel(dlg,
                text="💡  2-part: sube ambos archivos, luego ve a Editar Perfil → Artwork Showcase\n"
                     "     → activa layout de 2 columnas y asigna cada imagen a su slot.",
                text_color="#f59e0b", font=("Segoe UI", 10), justify="left",
            ).pack(anchor="w", padx=14, pady=(0, 4))

        btns = ctk.CTkFrame(dlg, fg_color="transparent")
        btns.pack(fill="x", padx=14, pady=8)

        copy_btn = ctk.CTkButton(btns, text="📋 Copiar JS", width=120)
        def _copy_js():
            dlg.clipboard_clear()
            dlg.clipboard_append(js_code)
            copy_btn.configure(text="✅ Copiado!")
            dlg.after(2000, lambda: copy_btn.configure(text="📋 Copiar JS"))
        copy_btn.configure(command=_copy_js)
        copy_btn.pack(side="left", padx=4)

        def _open_folder():
            try:
                os.startfile(str(frag_dir))
            except Exception:
                pass
        ctk.CTkButton(btns, text="📁 Abrir carpeta", command=_open_folder,
                      width=130).pack(side="left", padx=4)

        ctk.CTkButton(btns, text="🚀 Abrir Upload Tool",
                      command=lambda f=list(fragments), p=preset: (dlg.destroy(), self._launch_upload_tool(f, preset=p)),
                      fg_color="#16a34a", hover_color="#15803d",
                      width=160).pack(side="left", padx=4)

        ctk.CTkButton(btns, text="Cerrar", command=dlg.destroy,
                      fg_color="#555", width=80).pack(side="right", padx=4)

    def _show_artwork_result_dialog(self, panels: list):
        """Show the post-fragmentation dialog for the 2-panel Artwork Showcase layout.

        Displays the generated panel files, the upload JS snippet, and layout instructions.
        """
        if not panels:
            return
        frag_dir = panels[0].parent
        dlg = ctk.CTkToplevel(self.root)
        dlg.title("Artwork Showcase Listo")
        dlg.geometry("580x420")
        dlg.grab_set()

        ctk.CTkLabel(dlg, text="Artwork Showcase completado",
                     font=("Segoe UI", 14, "bold")).pack(pady=(14, 4))
        ctk.CTkLabel(dlg,
            text="Subir como: artwork (file_type=3)  |  506px main + 100px side",
            text_color="#888", font=("Segoe UI", 10)).pack()

        flist = ctk.CTkScrollableFrame(dlg, height=80, label_text="Paneles generados")
        flist.pack(fill="x", padx=14, pady=(6, 4))
        for f in panels:
            mb = f.stat().st_size / (1024 * 1024)
            ctk.CTkLabel(flist, text=f"  {f.name}  —  {mb:.2f} MB",
                         anchor="w", font=("Consolas", 10)).pack(anchor="w", padx=6, pady=1)

        _js_artwork = (
            "$J('[name=consumer_app_id]').val(767);\n"
            "$J('[name=file_type]').val(3);\n"
            "$J('[name=visibility]').val(0);"
        )
        ctk.CTkLabel(dlg, text="Consola del navegador (F12 → Console) — pega ANTES de guardar:",
                     font=("Segoe UI", 10, "bold"), anchor="w").pack(anchor="w", padx=14, pady=(6, 0))
        js_box = ctk.CTkTextbox(dlg, height=60, font=("Consolas", 10))
        js_box.pack(fill="x", padx=14, pady=(2, 2))
        js_box.insert("end", _js_artwork)
        js_box.configure(state="disabled")

        ctk.CTkLabel(dlg,
            text="  Sube ambos archivos, luego ve a Editar Perfil → Artwork Showcase\n"
                 "  → activa layout 2 columnas y asigna main y side a cada slot.",
            text_color="#f59e0b", font=("Segoe UI", 10), justify="left",
        ).pack(anchor="w", padx=14, pady=(0, 6))

        btns = ctk.CTkFrame(dlg, fg_color="transparent")
        btns.pack(fill="x", padx=14, pady=6)

        copy_btn = ctk.CTkButton(btns, text="📋 Copiar JS", width=110)
        def _copy_js():
            dlg.clipboard_clear()
            dlg.clipboard_append(_js_artwork)
            copy_btn.configure(text="✅ Copiado!")
            dlg.after(2000, lambda: copy_btn.configure(text="📋 Copiar JS"))
        copy_btn.configure(command=_copy_js)
        copy_btn.pack(side="left", padx=4)

        def _open_folder():
            try:
                os.startfile(str(frag_dir))
            except Exception:
                pass
        ctk.CTkButton(btns, text="📁 Abrir carpeta", command=_open_folder,
                      width=130).pack(side="left", padx=4)
        ctk.CTkButton(btns, text="🚀 Abrir Upload Tool",
                      command=lambda f=panels: (dlg.destroy(), self._launch_upload_tool(f, preset="artwork_2part")),
                      fg_color="#16a34a", hover_color="#15803d",
                      width=160).pack(side="left", padx=4)
        ctk.CTkButton(btns, text="Cerrar", command=dlg.destroy,
                      fg_color="#555", width=80).pack(side="right", padx=4)

    def _pick_showcase_preset(self) -> Optional[str]:
        """Modal dialog to pick a showcase preset. Uses dlg.wait_window() to block until closed.

        Returns the selected preset key string, or None if the user cancelled.
        """
        presets = self.processor.SHOWCASE_PRESETS
        dlg = ctk.CTkToplevel(self.root if hasattr(self, 'root') else None)
        dlg.title("Elegir preset de Showcase")
        dlg.geometry("560x460")
        dlg.grab_set()
        ctk.CTkLabel(dlg, text="Elige cómo fragmentar el GIF:",
                     font=("Segoe UI", 13, "bold")).pack(pady=(14, 6))
        chosen = {"val": None}
        var = ctk.StringVar(value="")
        scroll = ctk.CTkScrollableFrame(dlg, height=320)
        scroll.pack(fill="both", expand=True, padx=14, pady=6)
        for key, cfg in presets.items():
            hint = cfg.get("upload_hint", "?")
            txt = f"{key}  —  {cfg['desc']}  [upload: {hint}]"
            ctk.CTkRadioButton(scroll, text=txt, variable=var, value=key).pack(
                anchor="w", padx=8, pady=4)
        btns = ctk.CTkFrame(dlg, fg_color="transparent")
        btns.pack(fill="x", padx=14, pady=10)
        def _ok():
            chosen["val"] = var.get() or None
            dlg.destroy()
        def _cancel():
            chosen["val"] = None
            dlg.destroy()
        ctk.CTkButton(btns, text="OK", command=_ok,
                      fg_color="#16a34a", hover_color="#15803d").pack(side="right", padx=4)
        ctk.CTkButton(btns, text="Cancelar", command=_cancel,
                      fg_color="#7f1d1d", hover_color="#991b1b").pack(side="right", padx=4)
        dlg.wait_window()
        return chosen["val"]

    def _optimize_with_ffmpeg_aggressive(self, fragment_path, target_size_mb, max_size_mb):
        """Aggressive FFmpeg optimisation variant for very small fragments (size_multiplier > 3).

        Uses higher fps targets and sharpening filters compared to _optimize_with_ffmpeg_robust.
        Same best-result tracking pattern: keeps the closest partial result if no strategy
        hits the exact target range.
        """
        try:
            if not self.processor.check_ffmpeg():
                self.log_message(f"   FFmpeg no disponible")
                return False

            current_size_mb = fragment_path.stat().st_size / (1024 * 1024)
            size_multiplier = target_size_mb / current_size_mb

            self.log_message(f"   FFmpeg: {current_size_mb:.2f} → {target_size_mb:.2f} MB (x{size_multiplier:.1f})")

            # Higher fps and unsharp filters are used for larger required size increases.
            if size_multiplier > 5:
                strategies = [
                    "fps=60,split[s0][s1];[s0]palettegen=max_colors=256:stats_mode=single[p];[s1][p]paletteuse=dither=none",
                    "fps=48,unsharp=3:3:0.8,split[s0][s1];[s0]palettegen=max_colors=256[p];[s1][p]paletteuse=dither=floyd_steinberg",
                    "fps=40,scale=iw*1.1:ih*1.1:flags=lanczos,scale=iw/1.1:ih/1.1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=256[p];[s1][p]paletteuse=dither=sierra2_4a"
                ]
            elif size_multiplier > 3:
                strategies = [
                    "fps=45,split[s0][s1];[s0]palettegen=max_colors=256[p];[s1][p]paletteuse=dither=floyd_steinberg",
                    "fps=36,unsharp=2:2:0.6,split[s0][s1];[s0]palettegen=max_colors=224[p];[s1][p]paletteuse=dither=sierra2",
                    "fps=32,split[s0][s1];[s0]palettegen=max_colors=256:stats_mode=diff[p];[s1][p]paletteuse=dither=bayer:bayer_scale=2"
                ]
            else:
                strategies = [
                    "fps=30,split[s0][s1];[s0]palettegen=max_colors=256[p];[s1][p]paletteuse=dither=floyd_steinberg",
                    "split[s0][s1];[s0]palettegen=max_colors=256:stats_mode=single[p];[s1][p]paletteuse=dither=bayer:bayer_scale=3",
                    "unsharp=1:1:0.5,split[s0][s1];[s0]palettegen=max_colors=224[p];[s1][p]paletteuse=dither=sierra2_4a"
                ]

            # Probar estrategias
            best_result = None
            best_size = current_size_mb

            for i, strategy in enumerate(strategies):
                temp_path = fragment_path.with_suffix(f'.ffmpeg_opt_{i}.gif')

                try:
                    cmd = [
                        "ffmpeg", "-i", str(fragment_path), "-vf", strategy,
                        "-avoid_negative_ts", "make_zero", "-y", str(temp_path)
                    ]

                    result = subprocess.run(cmd, capture_output=True, text=True, timeout=90, **_NO_WINDOW_FLAGS)

                    if result.returncode == 0 and temp_path.exists():
                        new_size_mb = temp_path.stat().st_size / (1024 * 1024)
                        self.log_message(f"   Estrategia {i+1}: {new_size_mb:.2f} MB")

                        # ¿Cumple objetivo?
                        if target_size_mb <= new_size_mb <= max_size_mb:
                            shutil.move(temp_path, fragment_path)
                            self.log_message(f"   ✅ ÉXITO estrategia {i+1}!")
                            return True

                        # ¿Es mejor que lo anterior?
                        elif new_size_mb > best_size and new_size_mb <= max_size_mb:
                            if best_result and best_result.exists():
                                best_result.unlink()
                            best_result = temp_path
                            best_size = new_size_mb
                        else:
                            temp_path.unlink()
                    else:
                        if temp_path.exists():
                            temp_path.unlink()

                except Exception:
                    if temp_path.exists():
                        temp_path.unlink()

            # ¿Hay algún resultado útil?
            if best_result and best_result.exists() and best_size > current_size_mb:
                improvement = best_size - current_size_mb
                if improvement >= 0.1:
                    shutil.move(best_result, fragment_path)
                    self.log_message(f"   ✅ Mejor resultado: {current_size_mb:.2f} → {best_size:.2f} MB")
                    return True
                else:
                    best_result.unlink()

            return False

        except Exception as e:
            self.log_message(f"   ❌ Error FFmpeg: {e}")
            return False

    def fragment_for_steam_ffmpeg_only(self):
        """Fragment using FFmpeg only (no AI upscaling), with automatic batch optimisation.

        Faster than the AI pipeline. Uses shared-strategy batch optimisation so all 5 parts
        maintain visual consistency. Prompts for confirmation before starting.
        """
        if not self.current_file:
            self._ui_warn("Advertencia", "Primero selecciona un archivo")
            return

        def process():
            self._raise_if_cancelled()
            try:
                self.update_status("Verificando archivo...", 10, "🔍")
                self.log_message("=== FRAGMENTACIÓN STEAM (SOLO FFMPEG) ===", "INFO")
                self.log_message(f"Archivo: {self.current_file.name}")

                # Convertir a GIF si es necesario
                if self.current_file.suffix.lower() != '.gif':
                    self.log_message("Convirtiendo a GIF...")
                    gif_path = self.current_file.with_suffix('.gif')
                    gif_path = self.processor.convert_video_to_gif(self.current_file, gif_path)
                    if not gif_path:
                        raise Exception("Error convirtiendo a GIF")
                    self.current_file = gif_path

                # Fragmentar
                self.update_status("Fragmentando...", 30, "✂️")
                success = self.processor.split_gif_for_steam(self.current_file)

                if not success:
                    raise Exception("Error en fragmentación")

                # Analizar fragmentos desde el workspace real
                self.update_status("Analizando fragmentos...", 50, "📊")
                fragments = self.processor.list_fragments(self.current_file, "_part_")
                if not fragments:
                    raise Exception("No se encontraron fragmentos en el workspace tras la fragmentación")

                min_size = 4.7
                max_size = 5.0
                fragments_info = []

                for idx, frag in enumerate(fragments, 1):
                    size_mb = frag.stat().st_size / (1024 * 1024)
                    fragments_info.append({"part": idx, "path": frag, "size": size_mb})
                    status = "✅ ÓPTIMO" if min_size <= size_mb <= max_size else ("⚠️ GRANDE" if size_mb > max_size else "⚠️ PEQUEÑO")
                    self.log_message(f"Fragmento {idx}: {size_mb:.2f} MB {status}")

                # Batch optimisation: a single shared FFmpeg strategy is applied to all fragments
                # at once so palette and timing stay in sync across parts.
                needs_opt = [f for f in fragments_info
                             if f["size"] > max_size or f["size"] < min_size]

                if needs_opt:
                    self.update_status("Optimizando en lote (estrategia compartida)...", 70, "🔧")
                    self.log_message(f"🔧 Optimizando {len(fragments_info)} fragmentos con estrategia compartida...")
                    outputs = self.processor.shrink_batch_to_size_cap(
                        [f['path'] for f in fragments_info],
                        max_mb=max_size, min_mb=min_size,
                        progress_cb=lambda m: self.log_message(f"   {m}")
                    )
                    optimized_count = sum(1 for o in outputs if o)
                    self.log_message(f"Optimizados: {optimized_count}/{len(fragments_info)}")

                # Resultado final
                self.update_status("¡Fragmentación completada!", 100, "✅")
                self._show_final_fragments_report(self.current_file, min_size, max_size)

            except Exception as e:
                self.update_status("Error", 0, "❌")
                self.log_message(f"ERROR: {e}", "ERROR")
                self._ui_error("Error", f"Error: {e}")

        # Confirmación
        if messagebox.askyesno("Fragmentación FFmpeg", 
                              f"¿Fragmentar usando solo FFmpeg?\n\n" +
                              f"📁 {self.current_file.name}\n" +
                              f"🔧 Optimización automática\n" +
                              f"⚡ Sin procesamiento IA (más rápido)\n\n" +
                              f"¿Continuar?"):
            self._run_cancellable(process)



# ---------------------------------------------------------------------------
# PRO feature patch — loaded at module import time.
#
# Pattern: GUIMethodsMixin defines stub methods (process_full_ai, enhance_animation,
# _fragment_workshop_flow) that show an upgrade prompt on the free tier. When the
# private _pro_features module IS present (compiled PRO exe or local dev build), the
# real implementations are monkey-patched directly onto the class, replacing the stubs
# without changing any call sites.
#
# _pro_features.py is gitignored and not included in the public GitHub repo; the
# ImportError branch is the normal code path for open-source users.
# ---------------------------------------------------------------------------
try:
    import _pro_features as _pf
    GUIMethodsMixin.process_full_ai = _pf.process_full_ai
    GUIMethodsMixin._fragment_workshop_flow = _pf.fragment_workshop_flow
    GUIMethodsMixin.enhance_animation = _pf.enhance_animation
except ImportError:
    pass  # running free/public build — stubs remain in place

"""
gui_methods.py - Mixin con metodos de funcionalidad de la GUI
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
_NO_WINDOW_FLAGS = {'creationflags': subprocess.CREATE_NO_WINDOW} if platform.system() == 'Windows' else {}

_STATIC_IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.bmp', '.webp'}


def _steam_format_suggestion(w: int, h: int) -> Optional[str]:
    """Delegates to ContentAnalyzer._get_upload_suggestion — single source of truth."""
    if h <= 0:
        return None
    return _ContentAnalyzer._get_upload_suggestion(w, h)


class GUIMethodsMixin:
    """Mixin que aporta toda la funcionalidad de procesamiento a la GUI."""

    def setup_logging(self):
        """Configurar logger basico (Windows-safe: forzar UTF-8 para evitar UnicodeEncodeError con emojis)"""
        import logging, sys, io
        # Reconfigurar stdout/stderr a UTF-8 en Windows para permitir emojis
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
            # Filtro defensivo: reemplazar caracteres no codificables
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

        # Variables para animacion GIF
        self._gif_frames = []
        self._gif_frame_index = 0
        self._gif_frame_delay = 100
        self._gif_after_id = None

    def create_tooltip(self, widget, text):
        """Crear tooltip moderno"""
        def on_enter(event):
            tooltip = tk.Toplevel()
            tooltip.wm_overrideredirect(True)
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
        """Oscurecer un color para efecto hover"""
        # Convertir hex a RGB
        color = color.lstrip('#')
        r, g, b = tuple(int(color[i:i+2], 16) for i in (0, 2, 4))

        # Oscurecer 20%
        r = int(r * 0.8)
        g = int(g * 0.8)
        b = int(b * 0.8)

        return f'#{r:02x}{g:02x}{b:02x}'

    @staticmethod
    def _lazy_moviepy():
        """Lazy-import moviepy VideoFileClip (slow import, only load when needed)."""
        from moviepy.editor import VideoFileClip
        return VideoFileClip

    def _run_cancellable(self, process_fn):
        """Run a processing function in a thread with cancel-button UI management."""
        if hasattr(self, '_cancel_event'):
            self._cancel_event.clear()
        def wrapper():
            self.update_queue.put((self._show_cancel_btn, ()))
            try:
                process_fn()
            except InterruptedError:
                self.update_status("Cancelado", 0, "🛑")
                self.log_message("Procesamiento cancelado por el usuario", "WARN")
            finally:
                self.update_queue.put((self._hide_cancel_btn, ()))
        threading.Thread(target=wrapper, daemon=True).start()

    def _raise_if_cancelled(self):
        """Raise InterruptedError if user requested cancel. Use between long steps."""
        if self._is_cancelled():
            raise InterruptedError("Cancelled by user")

    def _is_cancelled(self):
        """True if user has requested cancellation."""
        return hasattr(self, '_cancel_event') and self._cancel_event.is_set()

    def _ui_info(self, title, msg):
        self.root.after(0, lambda t=title, m=msg: messagebox.showinfo(t, m))

    def _ui_warn(self, title, msg):
        self.root.after(0, lambda t=title, m=msg: messagebox.showwarning(t, m))

    def _ui_error(self, title, msg):
        self.root.after(0, lambda t=title, m=msg: messagebox.showerror(t, m))

    def _launch_upload_tool(self, fragments=None):
        try:
            flags = _NO_WINDOW_FLAGS
            frag_args = (["--fragments"] + [str(f) for f in fragments]) if fragments else []
            if getattr(sys, 'frozen', False):
                subprocess.Popen([sys.executable, "--upload-tool"] + frag_args, **flags)
            else:
                upload_tool_path = Path(__file__).parent.parent / "upload_tool.py"
                if not upload_tool_path.exists():
                    messagebox.showerror("Error", "upload_tool.py no encontrado.")
                    return
                subprocess.Popen([sys.executable, str(upload_tool_path)] + frag_args,
                                 cwd=str(upload_tool_path.parent), **flags)
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo abrir el Upload Tool:\n{e}")

    def update_ui_loop(self):
        """Loop para actualizar UI desde threads"""
        try:
            while not self.update_queue.empty():
                func, args = self.update_queue.get_nowait()
                func(*args)
        except Exception:
            pass

        self.root.after(100, self.update_ui_loop)

    # Métodos principales de funcionalidad

    def log_message(self, message, level="INFO"):
        """Agregar mensaje al log con formato"""
        timestamp = datetime.now().strftime("%H:%M:%S")

        # CTkTextbox: insertar texto plano (no soporta tags de color)
        line = f"[{timestamp}] {level}: {message}\n"
        self.process_log.insert("end", line)
        try:
            self.process_log.see("end")
        except Exception:
            pass

        # Log también a archivo
        if level == "ERROR":
            self.logger.error(message)
        elif level == "WARNING":
            self.logger.warning(message)
        else:
            self.logger.info(message)

    def update_status(self, message, progress=None, icon="⏳"):
        """Actualizar estado con animación"""
        def update():
            self.status_var.set(message)
            self.status_icon.configure(text=icon)
            if progress is not None:
                self.progress_var.set(progress / 100.0 if progress > 1 else progress)

        self.update_queue.put((update, ()))

    def update_system_status(self, system, status, state="warning"):
        """Actualizar indicador de estado del sistema"""
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
        """Verificar dependencias del sistema - MEJORADO"""
        def check():
            try:
                # Verificar GPU (resultado cacheado tras la primera llamada)
                self.log_message("Verificando GPU...", "INFO")
                gpu_available, gpu_info = self.processor.check_gpu_available()

                if gpu_available:
                    self._detected_gpu = gpu_info
                    self.update_system_status("gpu", gpu_info, "success")
                    self.log_message(f"GPU detectada: {gpu_info}", "SUCCESS")
                else:
                    self._detected_gpu = None
                    self.update_system_status("gpu", "No detectada", "warning")
                    self.log_message("GPU no detectada, usando CPU", "WARNING")

                # Verificar FFmpeg
                if self.processor.check_ffmpeg():
                    self.update_system_status("ffmpeg", "Disponible", "success")
                    self.log_message("FFmpeg disponible", "SUCCESS")
                else:
                    self.update_system_status("ffmpeg", "No encontrado", "error")
                    self.log_message("FFmpeg no encontrado - Algunas funciones limitadas", "WARNING")

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
        """Actualizar combo de modelos disponibles"""
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
        """Actualizar información del modelo seleccionado"""
        selected = self.model_combo.get()
        if not selected:
            return

        model_id = selected.split(" - ")[0]
        info = self.processor.model_manager.get_model_info(model_id)

        # Limpiar frame anterior
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
        """Seleccionar archivo con análisis automático"""
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

            # Análisis automático si está activado
            if self.auto_detect_var.get():
                self.analyze_content()

    # PARTE 2/3 - CONTINÚA DESDE select_file()

    def _stop_gif_animation(self):
        """Detener animacion GIF en curso"""
        if hasattr(self, '_gif_after_id') and self._gif_after_id:
            try:
                self.root.after_cancel(self._gif_after_id)
            except Exception:
                pass
            self._gif_after_id = None
        self._gif_frames = []
        self._gif_frame_index = 0

    # Límites del preview de video (tuneados para no comerse la RAM)
    _VIDEO_PREVIEW_MAX_FRAMES = 240      # cap duro en nº de PhotoImage en memoria
    _VIDEO_PREVIEW_MIN_FPS = 8           # bajo esto el preview se ve a tirones
    _VIDEO_PREVIEW_MAX_FPS = 24          # no tiene sentido ir más alto para un preview
    _VIDEO_PREVIEW_THUMB = (375, 250)    # tamaño final del thumbnail

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

                    # FPS objetivo: cubrir la duración completa sin pasarse del cap
                    target_fps = self._VIDEO_PREVIEW_MAX_FRAMES / duration
                    target_fps = max(self._VIDEO_PREVIEW_MIN_FPS,
                                     min(self._VIDEO_PREVIEW_MAX_FPS, target_fps))
                    delay_ms = max(20, int(1000 / target_fps))

                    thumb = self._VIDEO_PREVIEW_THUMB
                    for i, arr in enumerate(clip.iter_frames(fps=target_fps, dtype='uint8')):
                        if i >= self._VIDEO_PREVIEW_MAX_FRAMES:
                            break
                        # Aún si el usuario cambió de archivo, abortar
                        if self.current_file != video_file:
                            return
                        frame_img = Image.fromarray(arr)
                        frame_img.thumbnail(thumb, Image.Resampling.LANCZOS)
                        frames.append(frame_img.convert('RGBA'))

                # Volver a main thread para crear PhotoImage y mostrar
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
                        label.image = self._gif_frames[0]
                        label.pack()
                        if len(self._gif_frames) > 1:
                            self._gif_after_id = self.root.after(
                                self._gif_frame_delay, self._animate_gif, label)
                    except Exception as e:
                        self.log_message(f"Error mostrando preview: {e}", "WARNING")
                    finally:
                        # Liberar las imágenes PIL fuente; PhotoImage ya copió los datos
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
        """Avanzar al siguiente frame del GIF animado"""
        try:
            frames = self._gif_frames
            if not frames or not label.winfo_exists():
                return
            self._gif_frame_index = (self._gif_frame_index + 1) % len(frames)
            photo = frames[self._gif_frame_index]
            label.configure(image=photo)
            label.image = photo
            self._gif_after_id = self.root.after(self._gif_frame_delay, self._animate_gif, label)
        except Exception:
            pass

    def show_file_info(self):
        """Mostrar informacion del archivo con preview animado para GIFs"""
        if not self.current_file:
            return

        # Detener animacion anterior
        self._stop_gif_animation()

        # Limpiar info anterior
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
                # Extraer frames para animacion (con limite para evitar leak de memoria).
                # Si el GIF ya tiene el trailer patcheado para Steam (0x21 en vez de
                # 0x3B), Pillow no puede decodificarlo → leemos los bytes y
                # restauramos el trailer en memoria antes de abrir.
                self._gif_frames = []
                self._gif_frame_index = 0
                MAX_PREVIEW_FRAMES = 60
                try:
                    _gif_src = self.current_file
                    _gif_bytes = _gif_src.read_bytes()
                    if _gif_bytes and _gif_bytes[-1] == 0x21:
                        _gif_src = io.BytesIO(_gif_bytes[:-1] + b"\x3B")
                    gif_open_target = _gif_src
                except Exception:
                    gif_open_target = self.current_file
                with Image.open(gif_open_target) as gif_img:
                    self._gif_frame_delay = gif_img.info.get('duration', 100)
                    if self._gif_frame_delay < 20:
                        self._gif_frame_delay = 100

                    for i, frame in enumerate(ImageSequence.Iterator(gif_img)):
                        if i >= MAX_PREVIEW_FRAMES:
                            break
                        resized = frame.convert('RGBA')
                        resized.thumbnail((375, 250), Image.Resampling.LANCZOS)
                        photo = ImageTk.PhotoImage(resized)
                        self._gif_frames.append(photo)
                gc.collect()

                if self._gif_frames:
                    preview_label = ctk.CTkLabel(preview_frame, text="", image=self._gif_frames[0])
                    preview_label.image = self._gif_frames[0]
                    preview_label.pack()
                    # Iniciar animacion
                    if len(self._gif_frames) > 1:
                        self._gif_after_id = self.root.after(
                            self._gif_frame_delay, self._animate_gif, preview_label)

            elif ext in ('.jpg', '.jpeg', '.png', '.bmp', '.webp'):
                # Mostrar preview de imagen estatica
                try:
                    with Image.open(self.current_file) as img:
                        img_preview = img.copy()
                    img_preview.thumbnail((375, 250), Image.Resampling.LANCZOS)
                    photo = ImageTk.PhotoImage(img_preview.convert('RGBA'))
                    preview_label = ctk.CTkLabel(preview_frame, text="", image=photo)
                    preview_label.image = photo
                    preview_label.pack()
                except Exception:
                    pass

            elif ext in ('.mp4', '.avi', '.mov', '.mkv', '.webm', '.m4v', '.flv'):
                # Preview animado del video completo (muestrea toda la duración, cap en memoria)
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

            if hasattr(self, 'content_analysis') and self.content_analysis:
                content_type = self.content_analysis.get('type', 'unknown')
                confidence = self.content_analysis.get('confidence', 0) * 100
                ctk.CTkLabel(info_frame,
                             text=f"Tipo: {content_type} ({confidence:.0f}%)",
                             font=("Segoe UI", 9, "bold"),
                             text_color=Colors.ACCENT).pack(anchor="w", pady=(10, 0))

            self.log_message(f"Archivo seleccionado: {self.current_file.name}")
            self.update_status("Archivo cargado", 100, "✅")

        except Exception as e:
            ctk.CTkLabel(self.file_info_frame, text=f"Error: {e}",
                         text_color=Colors.DANGER).pack(anchor="w")
            self.log_message(f"Error mostrando info del archivo: {e}", "ERROR")

    def analyze_content(self):
        """Analizar contenido y recomendar modelo"""
        if not self.current_file:
            return

        def analyze():
            try:
                self.update_status("Analizando contenido...", 50, "🔍")
                self.log_message("Analizando tipo de contenido...")

                # Realizar análisis
                self.content_analysis = self.processor.content_analyzer.analyze_content(self.current_file)

                # Obtener recomendación
                recommended_model = self.processor.model_manager.get_model_recommendation(self.content_analysis)

                # Actualizar UI
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

                    # Mostrar info actualizada
                    self.show_file_info()

                    # Log
                    content_type = self.content_analysis.get('type', 'unknown')
                    self.log_message(f"Tipo detectado: {content_type}", "SUCCESS")
                    self.log_message(f"Modelo recomendado: {recommended_model}", "SUCCESS")

                self.update_queue.put((update_ui, ()))
                self.update_status("Análisis completado", 100, "✅")

            except Exception as e:
                self.log_message(f"Error analizando contenido: {e}", "ERROR")
                self.update_status("Error en análisis", 0, "❌")

        threading.Thread(target=analyze, daemon=True).start()

    def download_models(self):
        """Descargar todos los modelos con progreso - MEJORADO"""
        def download():
            try:
                self.update_status("Preparando descarga...", 5, "📥")
                self.log_message("=== DESCARGA DE MODELOS ===", "INFO")
                self.log_message("Descargando 5 modelos de Real-ESRGAN...")

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
                              "💾 ~200 MB de descarga\n" +
                              "⏱️ 2-5 minutos según conexión\n\n" +
                              "¿Continuar?"):
            threading.Thread(target=download, daemon=True).start()

    def process_full_ai(self):
        """Procesamiento completo con IA + Reporte de Calidad - VERSIÓN COMPLETA CORREGIDA"""
        if not self.current_file:
            self._ui_warn("Advertencia", "Primero selecciona un archivo")
            return

        selected_model = self.model_var.get()
        if not selected_model:
            self._ui_warn("Advertencia", "Selecciona un modelo de IA")
            return

        def process():
            self._raise_if_cancelled()
            original_file = self.current_file  # 🆕 Guardar referencia original
            processed_file = None
            temp_dir = None
            upscaled_frames = None  # 🆕 Inicializar variable

            try:
                # Helper to check cancellation
                def check_cancel():
                    if self._cancel_event.is_set():
                        raise InterruptedError("Procesamiento cancelado por el usuario")

                self.update_status("Iniciando procesamiento con IA...", 5, "🤖")
                self.log_message("=== PROCESAMIENTO CON IA ===", "INFO")
                self.log_message(f"Archivo: {self.current_file.name}")
                self.log_message(f"Modelo: {selected_model}")

                use_gpu = self.gpu_var.get()
                gpu_name = getattr(self, '_detected_gpu', None) or "GPU"
                mode = f"GPU ({gpu_name})" if use_gpu else "CPU"
                self.log_message(f"Modo de procesamiento: {mode}")

                check_cancel()

                # CORRECCIÓN 1: Crear directorio temporal más robusto
                if getattr(sys, 'frozen', False):
                    base_temp = Path(sys.executable).parent / "temp"
                else:
                    base_temp = Path("temp")

                unique_id = str(uuid.uuid4())[:8]
                temp_dir = base_temp / f"process_{unique_id}"
                temp_dir.mkdir(parents=True, exist_ok=True)

                frames_dir = temp_dir / "frames"
                upscaled_dir = temp_dir / "upscaled"
                frames_dir.mkdir(exist_ok=True)
                upscaled_dir.mkdir(exist_ok=True)

                self.update_status("Preparando archivo...", 10, "📁")

                check_cancel()

                ext = self.current_file.suffix.lower()
                is_static_image = ext in ('.jpg', '.jpeg', '.png', '.bmp', '.webp')

                # Convertir video a GIF si es necesario
                if ext in ('.mp4', '.avi', '.mov', '.mkv', '.webm', '.m4v', '.flv'):
                    self.log_message("Convirtiendo video a GIF...")
                    gif_path = self.current_file.with_suffix('.gif')
                    gif_path = self.processor.convert_video_to_gif(self.current_file, gif_path, 24)
                    if not gif_path:
                        raise Exception("Error convirtiendo video a GIF")
                    self.current_file = gif_path
                    self.log_message(f"Video convertido: {gif_path.name}")

                check_cancel()

                self.update_status("Extrayendo frames...", 20, "🎞️")
                self.log_message("Extrayendo frames...")

                # Extraer frames
                if is_static_image:
                    # Static image: copy as single frame
                    with Image.open(self.current_file) as _img:
                        img = _img.convert('RGB')
                    frame_path = frames_dir / "frame_000000.png"
                    img.save(frame_path, "PNG")
                    frame_paths = [frame_path]
                    fps = 1
                    self.log_message("Imagen estatica: 1 frame")
                elif self.current_file.suffix.lower() == '.gif':
                    frame_paths, duration = self.processor.extract_gif_frames(self.current_file, frames_dir)
                    fps = 1000 / duration if duration else 24
                else:
                    fps = self.processor.extract_video_frames(self.current_file, frames_dir)
                    frame_paths = sorted(frames_dir.glob("*.png"))

                if not frame_paths:
                    raise Exception("Error extrayendo frames")

                self.log_message(f"Frames extraídos: {len(frame_paths)}, FPS: {fps:.1f}")

                check_cancel()

                self.update_status(f"Aplicando IA con {mode}...", 40, "🚀")

                # Callback para progreso
                def ai_progress(message, progress):
                    if progress:
                        self.update_status(message, 40 + (progress * 0.4), "🤖")
                    self.log_message(message)

                # 🆕 CORRECCIÓN CRÍTICA: Upscale con IA
                upscaled_frames = self.processor.upscale_frames_batch(
                    frames_dir, upscaled_dir, selected_model, 
                    use_gpu=use_gpu, progress_callback=ai_progress
                )

                if not upscaled_frames:
                    raise Exception("Error en el upscaling con IA")

                self.log_message(f"IA aplicada: {len(upscaled_frames)} frames mejorados", "SUCCESS")

                check_cancel()

                # CORRECCIÓN 2: Verificar frames antes de continuar
                if not isinstance(upscaled_frames, list) or len(upscaled_frames) == 0:
                    raise Exception("Lista de frames upscaleados está vacía")

                # Verificar que los frames existen
                valid_frames = []
                for frame_path in upscaled_frames:
                    if isinstance(frame_path, Path) and frame_path.exists():
                        valid_frames.append(frame_path)
                    else:
                        self.log_message(f"⚠️ Frame no válido: {frame_path}", "WARNING")

                if not valid_frames:
                    raise Exception("No hay frames válidos después del upscaling")

                upscaled_frames = valid_frames  # Usar solo frames válidos
                self.log_message(f"✅ Frames válidos: {len(upscaled_frames)}")

                # Aplicar mejoras adicionales si están activadas
                if self.enhance_colors_var.get():
                    self.update_status("Preparando mejoras de color...", 85, "🎨")
                    self.log_message("Mejoras de color se aplicarán al GIF final...")

                # Static image: save upscaled PNG directly
                if is_static_image:
                    self.update_status("Guardando imagen mejorada...", 90, "📦")
                    output_path = self.current_file.parent / f"{self.current_file.stem}_AI_4x.png"
                    shutil.copy2(str(upscaled_frames[0]), str(output_path))

                    if not output_path.exists():
                        raise Exception(f"Imagen no se guardó correctamente: {output_path}")

                    file_size = output_path.stat().st_size
                    self.log_message(f"✅ Imagen mejorada: {file_size / (1024*1024):.2f} MB")

                    # Apply color enhancements if enabled
                    if self.enhance_colors_var.get():
                        try:
                            with Image.open(output_path) as img:
                                rgb = img.convert('RGB')
                                rgb = ImageEnhance.Contrast(rgb).enhance(self.contrast_var.get())
                                rgb = ImageEnhance.Color(rgb).enhance(self.saturation_var.get())
                                rgb.save(output_path)
                            self.log_message("Mejoras de color aplicadas")
                        except Exception as ce:
                            self.log_message(f"Aviso: mejoras de color fallaron: {ce}", "WARNING")

                else:
                    self.update_status("Creando GIF final...", 90, "📦")

                    # CORRECCIÓN 3: Crear GIF mejorado con validaciones
                    _ai_dir = self.processor._workspace_dir(self.current_file, "ai_x4")
                    _ai_name = f"{self.current_file.stem}_AI_4x.gif"
                    self.processor._archive_before_overwrite(_ai_dir, keep_names=[_ai_name])
                    output_path = _ai_dir / _ai_name

                    gif_created = self.processor.create_optimized_gif(upscaled_frames, output_path, int(fps))

                    if not gif_created:
                        raise Exception("Error creando GIF optimizado")

                    # CORRECCIÓN 4: Verificar que el archivo existe y es válido
                    if not output_path.exists():
                        raise Exception(f"GIF no se creó correctamente: {output_path}")

                    file_size = output_path.stat().st_size
                    if file_size < 1024:  # Menos de 1KB = archivo corrupto
                        raise Exception(f"GIF creado está corrupto (tamaño: {file_size} bytes)")

                    self.log_message(f"✅ GIF base creado correctamente: {file_size / (1024*1024):.2f} MB")

                    # CORRECCIÓN 5: Aplicar mejoras con manejo robusto de errores
                    if self.enhance_colors_var.get():
                        try:
                            self.update_status("Aplicando mejoras de color...", 95, "🎨")
                            self.log_message("Aplicando mejoras de color...")

                            # Verificar que el archivo es un GIF válido antes de mejorar
                            try:
                                with Image.open(output_path) as test_img:
                                    if test_img.format != 'GIF':
                                        raise Exception(f"Archivo no es GIF válido: {test_img.format}")
                                    frame_count = getattr(test_img, 'n_frames', 0)
                                    if frame_count == 0:
                                        raise Exception("GIF no tiene frames válidos")
                                    self.log_message(f"GIF válido: {frame_count} frames")
                            except Exception as validation_error:
                                self.log_message(f"⚠️ GIF no válido para mejoras: {validation_error}", "WARNING")
                                raise Exception(f"GIF base corrupto: {validation_error}")

                            # Aplicar mejoras con timeout
                            enhanced_path = None
                            enhancement_error = None

                            def enhance_worker():
                                nonlocal enhanced_path, enhancement_error
                                try:
                                    enhanced_path = self.processor.enhance_colors(
                                        output_path,
                                        self.contrast_var.get(),
                                        self.saturation_var.get()
                                    )
                                except Exception as e:
                                    enhancement_error = e

                            # Ejecutar mejora con timeout de 60 segundos (daemon para que no bloquee cierre)
                            enhancement_thread = threading.Thread(target=enhance_worker, daemon=True)
                            enhancement_thread.start()
                            enhancement_thread.join(timeout=60)

                            if enhancement_thread.is_alive():
                                # Timeout - proceso muy lento
                                self.log_message("⚠️ Timeout en mejoras de color (>60s)", "WARNING")
                                self.log_message("Continuando sin mejoras de color...", "INFO")
                            elif enhancement_error:
                                # Error en el proceso
                                self.log_message(f"⚠️ Error en mejoras: {enhancement_error}", "WARNING")
                                self.log_message("Continuando sin mejoras de color...", "INFO")
                            elif enhanced_path and enhanced_path != output_path and enhanced_path.exists():
                                # Éxito - usar archivo mejorado
                                enhanced_size = enhanced_path.stat().st_size / (1024*1024)
                                self.log_message(f"✅ Mejoras aplicadas: {enhanced_size:.2f} MB", "SUCCESS")
                                output_path = enhanced_path
                            else:
                                # No se aplicaron mejoras (archivo igual)
                                self.log_message("ℹ️ No se requirieron mejoras de color", "INFO")

                        except Exception as color_error:
                            self.log_message(f"⚠️ Saltando mejoras de color: {color_error}", "WARNING")
                            # Continuar sin mejoras - no es crítico

                # CORRECCIÓN 6: Actualizar archivo final
                processed_file = output_path
                self.current_file = output_path

                # Verificación final
                final_size = output_path.stat().st_size / (1024 * 1024)
                if final_size < 0.1:  # Menos de 100KB es sospechoso
                    raise Exception(f"Archivo final muy pequeño: {final_size:.2f} MB")

                self.update_status("¡Procesamiento completado!", 100, "✅")

                # Actualizar UI
                def update_ui():
                    self.show_file_info()

                self.update_queue.put((update_ui, ()))

                self.log_message("=== PROCESAMIENTO COMPLETADO ===", "SUCCESS")
                self.log_message(f"Archivo final: {output_path.name}")
                self.log_message(f"Tamaño: {final_size:.2f} MB")

                try:
                    self.processor._write_manifest(output_path.parent, "procesar_ai_x4",
                        {"modelo": selected_model, "modo": mode, "fps": int(fps),
                         "mejorar_colores": bool(self.enhance_colors_var.get()),
                         "contraste": self.contrast_var.get(),
                         "saturacion": self.saturation_var.get()},
                        archivos=[output_path], fuente=self.current_file)
                except Exception:
                    pass

                # CORRECCIÓN 7: Reporte de calidad con manejo de errores
                try:
                    self.log_message("Generando reporte de calidad...", "INFO")
                    processing_details = {
                        "model": selected_model,
                        "mode": mode,
                        "enhance_colors": self.enhance_colors_var.get(),
                        "contrast": self.contrast_var.get(),
                        "saturation": self.saturation_var.get()
                    }

                    if hasattr(self, 'quality_reporter') and self.quality_reporter:
                        quality_report = self.quality_reporter.create_quality_report(
                            original_file, processed_file, processing_details
                        )

                        if quality_report:
                            self.log_message("Reporte de calidad generado", "SUCCESS")
                            # Mostrar reporte después de 1 segundo
                            self.root.after(1000, lambda: self.quality_reporter.show_quality_report_window(
                                quality_report, self.root
                            ))
                        else:
                            self.log_message("No se pudo generar reporte de calidad", "WARNING")
                    else:
                        self.log_message("Sistema de reportes no disponible", "INFO")

                except Exception as report_error:
                    self.log_message(f"Error en reporte de calidad: {report_error}", "WARNING")

                # Mensaje de éxito
                self._ui_info("¡Éxito!", 
                    f"¡Procesamiento completado exitosamente!\n\n" +
                    f"📁 Archivo: {output_path.name}\n" +
                    f"📊 Tamaño: {final_size:.2f} MB\n" +
                    f"🤖 Modelo: {selected_model}\n" +
                    f"⚡ Procesado con: {mode}\n\n" +
                    f"🎨 Mejoras aplicadas: {'Sí' if self.enhance_colors_var.get() else 'No'}\n" +
                    f"📊 Se abrirá el reporte de calidad...\n" +
                    f"¡Listo para fragmentar para Steam!")

            except InterruptedError:
                self.log_message("=== PROCESAMIENTO CANCELADO ===", "WARNING")
                self.update_status("Cancelado", 0, "🛑")
                self._ui_info("Cancelado", "Procesamiento cancelado correctamente.")

            except Exception as e:
                self.log_message(f"ERROR CRÍTICO: {e}", "ERROR")
                self.update_status("Error", 0, "❌")

                # Diagnóstico adicional
                if "upscaled_frames" in str(e) or upscaled_frames is None:
                    error_msg = f"Error en procesamiento con IA:\n\n{e}\n\n"
                    error_msg += "Posibles causas:\n"
                    error_msg += "• Modelo de IA no disponible\n"
                    error_msg += "• GPU no compatible\n"
                    error_msg += "• Frames de entrada corruptos\n"
                    error_msg += "• Memoria insuficiente\n\n"
                    error_msg += "Soluciones:\n"
                    error_msg += "• Verifica que el modelo esté descargado\n"
                    error_msg += "• Cambia a modo CPU\n"
                    error_msg += "• Usa archivo más pequeño\n"
                    error_msg += "• Reinicia WorkshopArt PRO"
                elif "GIF" in str(e) or "create_optimized_gif" in str(e):
                    error_msg = f"Error creando GIF final:\n\n{e}\n\n"
                    error_msg += "Posibles causas:\n"
                    error_msg += "• Frames de IA corruptos\n"
                    error_msg += "• Memoria insuficiente\n"
                    error_msg += "• Archivo original demasiado largo\n\n"
                    error_msg += "Soluciones:\n"
                    error_msg += "• Usar archivo más corto (<10s)\n"
                    error_msg += "• Cerrar otras aplicaciones\n"
                    error_msg += "• Reiniciar WorkshopArt PRO"
                else:
                    error_msg = f"Error en procesamiento:\n\n{e}"

                self._ui_error("Error", error_msg)

            finally:
                # CORRECCIÓN 8: Limpieza robusta
                try:
                    if temp_dir and temp_dir.exists():
                        shutil.rmtree(temp_dir, ignore_errors=True)
                        self.log_message("Archivos temporales limpiados")
                except Exception as cleanup_error:
                    self.log_message(f"Advertencia limpiando temporales: {cleanup_error}", "WARNING")

                self.update_status("Listo", 0, "✅")

        # Confirmación con información detallada
        model_info = self.processor.model_manager.get_model_info(selected_model)
        gpu_name = getattr(self, '_detected_gpu', None) or "GPU"
        mode = f"GPU ({gpu_name})" if self.gpu_var.get() else "CPU"
        quality = "Alta" if self.quality_var.get() == "Alta Calidad" else "Balanceada"

        if messagebox.askyesno("Confirmar Procesamiento", 
                              f"¿Procesar archivo con IA?\n\n" +
                              f"📁 Archivo: {self.current_file.name}\n" +
                              f"🤖 Modelo: {model_info.get('name', selected_model)}\n" +
                              f"⚡ Procesamiento: {mode}\n" +
                              f"🎨 Calidad: {quality}\n" +
                              f"⏱️ Tiempo estimado: 2-10 minutos\n\n" +
                              f"🎨 Mejoras de color: {'SÍ' if self.enhance_colors_var.get() else 'NO'}\n" +
                              f"📊 Se generará reporte de calidad\n\n" +
                              f"¿Continuar?"):
            self._run_cancellable(process)


    def enhance_colors_only(self):
        """Solo mejorar colores sin IA"""
        if not self.current_file:
            self._ui_warn("Advertencia", "Primero selecciona un archivo")
            return

        def process():
            self._raise_if_cancelled()
            try:
                self.update_status("Mejorando colores...", 50, "🎨")
                self.log_message("Aplicando mejoras de color...")
                self.log_message(f"Contraste: {self.contrast_var.get():.1f}")
                self.log_message(f"Saturación: {self.saturation_var.get():.1f}")

                enhanced_path = self.processor.enhance_colors(
                    self.current_file,
                    self.contrast_var.get(),
                    self.saturation_var.get()
                )

                if enhanced_path != self.current_file:
                    self.current_file = enhanced_path

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
        """Convertir MP4 a GIF con opciones personalizadas"""
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

        # Vincular eventos para actualizar estimación
        fps_var.trace_add("write", lambda *args: update_estimate())
        custom_fps_var.trace_add("write", lambda *args: update_estimate())
        quality_var.trace_add("write", lambda *args: update_estimate())
        resize_var.trace_add("write", lambda *args: update_estimate())
        custom_var.trace_add("write", lambda *args: update_estimate())

        update_estimate()  # Estimación inicial

        # Botones
        button_frame = ctk.CTkFrame(config_window, fg_color="transparent")
        button_frame.pack(fill="x", padx=20, pady=15)

        def start_conversion():
            config_window.destroy()

            # Obtener configuración
            fps = custom_fps_var.get() if custom_var.get() else fps_var.get()
            fps = max(1, min(60, fps))
            quality = quality_var.get()
            should_resize = resize_var.get()
            should_enhance = enhance_var.get()

            def process():
                self._raise_if_cancelled()
                try:
                    self.update_status("Convirtiendo video a GIF...", 20, "🎬")
                    self.log_message("=== CONVERSIÓN MP4 → GIF ===", "INFO")
                    self.log_message(f"Archivo: {self.current_file.name}")
                    self.log_message(f"FPS: {fps}")
                    self.log_message(f"Calidad: {quality}")
                    self.log_message(f"Redimensionar: {should_resize}")

                    # Determinar nombre del archivo de salida
                    _conv_dir = self.processor._workspace_dir(self.current_file, "convertido")
                    _conv_name = f"{self.current_file.stem}.gif"
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
                                archivos=[final_result], fuente=self.current_file)
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
    def enhance_animation(self):
        """Mejorar animación con múltiples opciones"""
        if not self.current_file:
            self._ui_warn("Advertencia", "Primero selecciona un archivo")
            return

        # Mostrar opciones de mejora
        option_window = ctk.CTkToplevel(self.root)
        option_window.title("Mejorar Animacion")
        option_window.geometry("420x340")
        option_window.transient(self.root)
        try:
            option_window.grab_set()
        except Exception:
            pass

        ctk.CTkLabel(option_window, text="Mejora de Animacion",
                     font=Fonts.HEADING,
                     text_color=Colors.ACCENT).pack(pady=(20, 10))

        options_frame = ctk.CTkFrame(option_window, fg_color="transparent")
        options_frame.pack(fill="both", expand=True, padx=20, pady=10)

        option_var = tk.StringVar(value="interpolate")

        for val, title, desc in [
            ("rife", "RIFE IA 2x (recomendado)", "Interpolacion con IA - maxima fluidez"),
            ("interpolate", "Interpolacion a 60 FPS", "Duplica/triplica frames para mayor fluidez"),
            ("smooth", "Suavizado de Movimiento", "Aplica motion blur suave"),
            ("optimize", "Optimizar Reproduccion", "Normaliza timing para reproduccion estable"),
        ]:
            ctk.CTkRadioButton(options_frame, text=title,
                               variable=option_var, value=val,
                               font=Fonts.SMALL, radiobutton_width=16,
                               radiobutton_height=16).pack(anchor="w", pady=(8, 0))
            ctk.CTkLabel(options_frame, text=f"  {desc}",
                         font=Fonts.CAPTION,
                         text_color=Colors.TEXT_MUTED).pack(anchor="w", padx=20)

        button_frame = ctk.CTkFrame(option_window, fg_color="transparent")
        button_frame.pack(fill="x", padx=20, pady=10)

        def execute_enhancement():
            selected_option = option_var.get()
            option_window.destroy()

            def process():
                self._raise_if_cancelled()
                try:
                    result = None
                    success_msg = ""
                    if selected_option == "rife":
                        self.update_status("Interpolando con RIFE IA...", 30, "🧠")
                        self.log_message("=== INTERPOLACIÓN RIFE 2x ===", "INFO")
                        if not getattr(self.processor, 'rife_path', None):
                            self._ui_warn(
                                "RIFE no encontrado",
                                "Falta rife-ncnn-vulkan.exe en el directorio del proyecto.\n\n"
                                "Descárgalo de: github.com/nihui/rife-ncnn-vulkan/releases\n"
                                "y colócalo junto al resto de ejecutables."
                            )
                            return
                        result = self.processor.interpolate_frames_rife(self.current_file, multiplier=2)
                        success_msg = "¡Interpolación RIFE 2x completada!"

                    elif selected_option == "interpolate":
                        self.update_status("Interpolando a 60 FPS...", 50, "⚡")
                        self.log_message("=== INTERPOLACIÓN A 60 FPS ===", "INFO")
                        result = self.processor.interpolate_frames_to_60fps(self.current_file)
                        success_msg = "¡Interpolación a 60 FPS completada!"

                    elif selected_option == "smooth":
                        self.update_status("Aplicando suavizado...", 50, "✨")
                        self.log_message("=== SUAVIZADO DE MOVIMIENTO ===", "INFO")
                        result = self.processor.create_motion_blur_effect(self.current_file)
                        success_msg = "¡Efecto de suavizado aplicado!"

                    elif selected_option == "optimize":
                        self.update_status("Optimizando reproducción...", 50, "🔧")
                        self.log_message("=== OPTIMIZACIÓN DE REPRODUCCIÓN ===", "INFO")
                        result = self.processor.optimize_gif_playback(self.current_file)
                        success_msg = "¡Reproducción optimizada!"

                    if result and result != self.current_file:
                        self.current_file = result

                        def update_ui():
                            self.show_file_info()

                        self.update_queue.put((update_ui, ()))

                        self.update_status("¡Mejora completada!", 100, "✅")
                        self.log_message(f"Archivo mejorado: {result.name}", "SUCCESS")

                        self._ui_info("¡Éxito!", 
                            f"{success_msg}\n\n" +
                            f"📁 Archivo: {result.name}\n" +
                            f"🎬 Mejora aplicada exitosamente")
                    else:
                        self.update_status("No se requieren cambios", 100, "ℹ️")
                        self._ui_info("Información", 
                            "El archivo ya está optimizado o no requiere cambios.")

                except Exception as e:
                    self.update_status("Error", 0, "❌")
                    self.log_message(f"ERROR: {e}", "ERROR")
                    self._ui_error("Error", f"Error en mejora: {e}")

            self._run_cancellable(process)

        ctk.CTkButton(button_frame, text="Aplicar",
                      command=execute_enhancement,
                      fg_color=Colors.ACCENT,
                      hover_color=Colors.ACCENT_DARK,
                      height=34, corner_radius=8).pack(side="right", padx=(10, 0))

        ctk.CTkButton(button_frame, text="Cancelar",
                      command=option_window.destroy,
                      fg_color="transparent", border_width=1,
                      border_color=Colors.BORDER,
                      hover_color=Colors.HOVER,
                      height=34, corner_radius=8).pack(side="right")

    def _show_optimization_dialog(self, fragments_info, min_size, max_size):
        """Mostrar diálogo de optimización simplificado"""
        small_count = sum(1 for f in fragments_info if f["size"] < min_size)
        large_count = sum(1 for f in fragments_info if f["size"] > max_size)

        if small_count == 0 and large_count == 0:
            return False  # No necesita optimización

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
        """Optimizar la calidad de un fragmento específico - VERSIÓN COMPLETAMENTE CORREGIDA"""
        try:
            current_size_mb = fragment_path.stat().st_size / (1024 * 1024)

            if current_size_mb >= target_size_mb:
                return True  # Ya está en el tamaño objetivo

            self.log_message(f"   Tamaño actual: {current_size_mb:.2f} MB, objetivo: {target_size_mb:.2f} MB")

            # ESTRATEGIA 1: FFmpeg con múltiples intentos (más confiable)
            success = self._optimize_with_ffmpeg_robust(fragment_path, target_size_mb, max_size_mb)
            if success:
                return True

            # ESTRATEGIA 2: PIL con manejo robusto de errores
            try:
                # Verificar que el archivo existe y es válido
                if not fragment_path.exists():
                    self.log_message(f"   Error: archivo no existe")
                    return False

                # Intentar abrir el GIF con múltiples métodos
                frames = []
                durations = []

                # MÉTODO 1: Usar ImageSequence.Iterator (más robusto)
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

                # PROCESAMIENTO: Calcular configuración para alcanzar tamaño objetivo
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

                # GUARDAR: Crear GIF mejorado con configuración robusta
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
        """FFmpeg con múltiples estrategias robustas - VERSIÓN MEJORADA"""
        try:
            # Verificar FFmpeg
            if not self.processor.check_ffmpeg():
                self.log_message(f"   FFmpeg no disponible")
                return False

            current_size_mb = fragment_path.stat().st_size / (1024 * 1024)
            size_multiplier = target_size_mb / current_size_mb

            # Estrategias más conservadoras y robustas
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
        """Función de compatibilidad - redirige a la versión robusta"""
        return self._optimize_with_ffmpeg_robust(fragment_path, target_size_mb, max_size_mb)


    def _cleanup_temp_files(self, fragment_path, exclude_index=None):
        """Limpiar archivos temporales de FFmpeg"""
        try:
            parent_dir = fragment_path.parent
            base_name = fragment_path.stem

            # Buscar y eliminar archivos temporales
            temp_patterns = [
                f"{base_name}.ffmpeg_tmp_*.gif",
                f"{base_name}.tmp*.gif"
            ]

            for pattern in temp_patterns:
                for temp_file in parent_dir.glob(pattern):
                    # No eliminar el archivo que acabamos de crear exitosamente
                    if exclude_index is not None and f"tmp_{exclude_index}" in temp_file.name:
                        continue
                    try:
                        temp_file.unlink()
                    except Exception:
                        pass
        except Exception:
            pass

    def _show_final_fragments_report(self, source_file, min_size, max_size):
        """Mostrar reporte final de fragmentos con diálogo enriquecido.
        `source_file` es el archivo fuente desde el que se generaron los
        fragmentos; se localizan en <stem>_workshop/fragmentos/."""
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

        # Diálogo enriquecido en main thread
        self.root.after(0, lambda: self._show_fragments_dialog(fragments_info, total_size, min_size, max_size))

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
        """Construir imagen preview del grid de Steam con gaps de 4px."""
        if not fragments_info:
            return None
        # Steam showcase: 5 fragmentos horizontales 638x354 con gap de 4px
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
        """Diálogo final de fragmentación con grid preview + botones de acción."""
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
        """Auto-subir a Steam Workshop los fragmentos marcados (uso personal).

        Requiere src/steam_uploader.py + steam_cookies.json (gitignorados).
        """
        # Import perezoso: módulo privado, puede no existir al publicar en GitHub
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

        # Ejecutar en thread
        def worker():
            def progress(i, total, msg):
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
        help_window.title(t("help_window_title", fallback="Ayuda - WorkshopArt PRO"))
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
        """Manejar cierre de aplicacion"""
        try:
            self._stop_gif_animation()
            # Limpiar archivos temporales (ruta según modo frozen o dev)
            if getattr(sys, 'frozen', False):
                temp_dir = Path(sys.executable).parent / "temp"
            else:
                temp_dir = Path("temp")
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
        self.log_message("🎮 WorkshopArt PRO v1.0 iniciado", "SUCCESS")
        self.log_message("✨ Versión modular con todas las funciones", "INFO")
        self.log_message("📁 Selecciona un archivo para comenzar", "INFO")

        # Ejecutar loop principal
        self.root.mainloop()

    def optimize_to_steam_limit(self):
        """Optimizar uno o varios GIFs para que pesen ≤5MB (límite de Steam Workshop).

        Rango objetivo por defecto: [4.5 MB, 5.0 MB] — mete la máxima calidad
        que Steam aceptará. El usuario puede ajustar max_mb vía diálogo.
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
        # Objetivo mínimo: 94% del máximo para mantener calidad alta
        min_mb = max(0.1, max_mb * 0.94)

        self.log_message(f"=== OPTIMIZACIÓN A ≤{max_mb:.2f} MB ({len(files)} archivos) ===", "INFO")

        def process():
            self._raise_if_cancelled()
            results: list[tuple[Path, Optional[Path], float, float]] = []
            try:
                originals = [(p, p.stat().st_size / (1024 * 1024)) for p in files]
                if len(files) > 1:
                    # Batch: estrategia compartida → fragmentos sincronizados
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
                    # Archivo único: optimizador individual con refinamiento de paleta
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
        """Fragmentar para Steam - elige formato Workshop o Artwork Showcase"""
        if not self.current_file:
            self._ui_warn("Advertencia", "Primero selecciona un archivo")
            return

        # Mostrar dialogo de seleccion de formato
        dialog = ctk.CTkToplevel(self.root)
        dialog.title("Seleccionar formato de fragmentación")
        dialog.geometry("420x310")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()

        # Centrar dialogo
        dialog.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - 420) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - 310) // 2
        dialog.geometry(f"+{x}+{y}")

        ctk.CTkLabel(
            dialog, text="¿Qué formato deseas?",
            font=("Segoe UI", 16, "bold")
        ).pack(pady=(20, 15))

        ctk.CTkLabel(
            dialog, text=f"Archivo: {self.current_file.name}",
            font=("Segoe UI", 11),
            text_color="#aaaaaa"
        ).pack(pady=(0, 15))

        def choose_workshop():
            dialog.destroy()
            self._fragment_workshop_flow()

        def choose_artwork():
            dialog.destroy()
            self.fragment_for_artwork_direct()

        # Boton Workshop Showcase
        ws_btn = ctk.CTkButton(
            dialog,
            text="Workshop Showcase (5 partes)\n638x354 px cada una",
            command=choose_workshop,
            height=50, corner_radius=8,
            font=("Segoe UI", 12),
            fg_color="#c0392b", hover_color="#962d22"
        )
        ws_btn.pack(fill="x", padx=30, pady=(0, 10))

        # Boton Artwork Showcase
        art_btn = ctk.CTkButton(
            dialog,
            text="Artwork Showcase (2 paneles)\n506x506 + 100x506 px",
            command=choose_artwork,
            height=50, corner_radius=8,
            font=("Segoe UI", 12),
            fg_color="#8e44ad", hover_color="#6c3483"
        )
        art_btn.pack(fill="x", padx=30, pady=(0, 10))

        # Boton cancelar
        ctk.CTkButton(
            dialog, text="Cancelar", command=dialog.destroy,
            height=32, corner_radius=8,
            font=("Segoe UI", 11),
            fg_color="transparent", hover_color="#333333",
            border_width=1, border_color="#555555"
        ).pack(pady=(5, 15))

    def _fragment_workshop_flow(self):
        """Flujo original de fragmentación Workshop con opción de preview"""
        show_preview = messagebox.askyesno(
            "Opciones de Fragmentación",
            f"¿Cómo quieres fragmentar {self.current_file.name}?\n\n" +
            f"👁️ SÍ: Ver preview primero\n" +
            f"✂️ NO: Fragmentar directamente\n\n" +
            f"Recomendado: Ver preview primero"
        )

        if show_preview:
            try:
                self.fragment_previewer.create_fragment_preview(self.current_file, self.root)
            except Exception as e:
                self._ui_error("Error en Preview", f"Error creando preview:\n{e}\n\nFragmentando directamente...")
                self.fragment_for_steam_direct()
        else:
            self.fragment_for_steam_direct()

    def fragment_for_steam_direct(self):
        """Fragmentación directa sin preview"""
        if not self.current_file:
            self._ui_warn("Advertencia", "Primero selecciona un archivo")
            return

        def process():
            self._raise_if_cancelled()
            try:
                self.update_status("Iniciando fragmentación...", 10, "✂️")
                self.log_message("=== FRAGMENTACIÓN DIRECTA ===", "INFO")
                self.log_message(f"Archivo: {self.current_file.name}")

                # Convertir a GIF si es necesario
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

                    # Localizar fragmentos reales en el workspace (<stem>_workshop/fragmentos/)
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
        """Fragmentación directa para Artwork Showcase (2 paneles: 506 + 100 px)"""
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

                    # Localizar paneles reales en el workspace
                    artwork_panels = self.processor.list_fragments(self.current_file, "artwork_")

                    if not artwork_panels:
                        raise Exception("No se encontraron paneles artwork en el workspace tras la fragmentación")

                    for frag in artwork_panels:
                        size_mb = frag.stat().st_size / (1024 * 1024)
                        self.log_message(f"Creado: {frag.name} ({size_mb:.2f} MB)", "SUCCESS")

                    self.root.after(0, lambda p=list(artwork_panels): self._show_artwork_result_dialog(p))

                else:
                    raise Exception("La fragmentación Artwork falló")

            except Exception as e:
                self.update_status("Error en fragmentación Artwork", 0, "❌")
                self.log_message(f"ERROR: {e}", "ERROR")
                self._ui_error("Error", f"Error en fragmentación Artwork:\n\n{e}")
            finally:
                self.update_status("Listo", 0, "✅")

        # Ejecutar en thread separado
        self._run_cancellable(process)

    def fragment_for_showcase_preset(self, preset: str = None):
        """Fragmentación genérica por preset de showcase.

        Si preset=None abre diálogo para elegir. Presets en SteamProcessor.SHOWCASE_PRESETS.
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
        """Diálogo de resultado de fragmentación con acciones rápidas."""
        upload_hint = cfg.get("upload_hint", "artwork")
        spoof = cfg.get("spoof_dims", False)

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
                      command=lambda f=list(fragments): (dlg.destroy(), self._launch_upload_tool(f)),
                      fg_color="#16a34a", hover_color="#15803d",
                      width=160).pack(side="left", padx=4)

        ctk.CTkButton(btns, text="Cerrar", command=dlg.destroy,
                      fg_color="#555", width=80).pack(side="right", padx=4)

    def _show_artwork_result_dialog(self, panels: list):
        """Result dialog for Artwork Showcase fragmentation with direct upload shortcut."""
        if not panels:
            return
        frag_dir = panels[0].parent
        dlg = ctk.CTkToplevel(self.root)
        dlg.title("Artwork Showcase Listo")
        dlg.geometry("520x280")
        dlg.grab_set()

        ctk.CTkLabel(dlg, text="Artwork Showcase completado",
                     font=("Segoe UI", 14, "bold")).pack(pady=(14, 4))

        flist = ctk.CTkScrollableFrame(dlg, height=100, label_text="Paneles generados")
        flist.pack(fill="x", padx=14, pady=(0, 8))
        for f in panels:
            mb = f.stat().st_size / (1024 * 1024)
            ctk.CTkLabel(flist, text=f"  {f.name}  —  {mb:.2f} MB",
                         anchor="w", font=("Consolas", 10)).pack(anchor="w", padx=6, pady=1)

        btns = ctk.CTkFrame(dlg, fg_color="transparent")
        btns.pack(fill="x", padx=14, pady=8)

        def _open_folder():
            try:
                os.startfile(str(frag_dir))
            except Exception:
                pass

        ctk.CTkButton(btns, text="📁 Abrir carpeta", command=_open_folder,
                      width=130).pack(side="left", padx=4)
        ctk.CTkButton(btns, text="🚀 Abrir Upload Tool",
                      command=lambda f=panels: (dlg.destroy(), self._launch_upload_tool(f)),
                      fg_color="#16a34a", hover_color="#15803d",
                      width=160).pack(side="left", padx=4)
        ctk.CTkButton(btns, text="Cerrar", command=dlg.destroy,
                      fg_color="#555", width=80).pack(side="right", padx=4)

    def _pick_showcase_preset(self) -> Optional[str]:
        """Diálogo modal para elegir preset de showcase."""
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
        """Optimización FFmpeg agresiva para fragmentos pequeños"""
        try:
            if not self.processor.check_ffmpeg():
                self.log_message(f"   FFmpeg no disponible")
                return False

            current_size_mb = fragment_path.stat().st_size / (1024 * 1024)
            size_multiplier = target_size_mb / current_size_mb

            self.log_message(f"   FFmpeg: {current_size_mb:.2f} → {target_size_mb:.2f} MB (x{size_multiplier:.1f})")

            # Estrategias según el incremento necesario
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
        """Fragmentación usando SOLO FFmpeg, sin IA"""
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

                # Optimizar en lote compartiendo estrategia (evita desincronización)
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


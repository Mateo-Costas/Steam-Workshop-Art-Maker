"""ui.logic.files - file selection, animated previews and content analysis."""
import gc
import io
import threading
from pathlib import Path

import customtkinter as ctk
from tkinter import filedialog
from PIL import Image, ImageTk, ImageSequence

from theme_PRO import Colors, Fonts
from ui.logic.common import _steam_format_suggestion


class FilesMixin:
    """File picking, metadata display and GIF/video preview playback."""

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



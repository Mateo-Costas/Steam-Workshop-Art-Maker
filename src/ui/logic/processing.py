"""ui.logic.processing - color enhancement, MP4->GIF conversion and PRO stubs.

The PRO build replaces process_full_ai / enhance_animation via the
_pro_features patch applied in ui.logic.__init__.
"""
import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk

from theme_PRO import Colors, Fonts


class ProcessingMixin:
    """Non-AI processing actions plus the free-tier stubs for PRO features."""

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

        # Recorte (trim): elegir el segmento del video a convertir
        ctk.CTkLabel(main_frame, text="Recorte del video",
                     font=("Segoe UI", 10, "bold"),
                     text_color=Colors.TEXT).pack(anchor="w", pady=(15, 5))

        trim_start_var = tk.DoubleVar(value=0.0)
        trim_end_var = tk.DoubleVar(value=float(duration))
        trim_label = ctk.CTkLabel(main_frame, text="", font=Fonts.CAPTION,
                                  text_color=Colors.TEXT_SECONDARY)

        def _update_trim_label(*_args):
            start, end = trim_start_var.get(), trim_end_var.get()
            if end <= start:  # keep at least 0.5 s of clip
                trim_end_var.set(min(float(duration), start + 0.5))
                end = trim_end_var.get()
            trim_label.configure(
                text=f"Desde {start:.1f}s hasta {end:.1f}s  →  {end - start:.1f}s de GIF")

        ctk.CTkSlider(main_frame, from_=0.0, to=max(0.5, float(duration)),
                      variable=trim_start_var).pack(fill="x", pady=(0, 2))
        ctk.CTkSlider(main_frame, from_=0.0, to=max(0.5, float(duration)),
                      variable=trim_end_var).pack(fill="x", pady=(0, 2))
        trim_label.pack(anchor="w")
        trim_start_var.trace_add("write", _update_trim_label)
        trim_end_var.trace_add("write", _update_trim_label)
        _update_trim_label()

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
                clip_len = max(0.5, trim_end_var.get() - trim_start_var.get())
                # Rough heuristic: ~0.02 MB per frame at 638x354 before quality adjustments.
                base_size = clip_len * fps * 0.02

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
            # Only pass trim bounds when the user actually moved the sliders.
            trim_start = trim_start_var.get() if trim_start_var.get() > 0.05 else None
            trim_end = (trim_end_var.get()
                        if trim_end_var.get() < float(duration) - 0.05 else None)

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

                    if trim_start is not None or trim_end is not None:
                        self.log_message(
                            f"Recorte: {trim_start or 0:.1f}s → "
                            f"{trim_end if trim_end else 'fin'}")

                    # Convertir usando el procesador
                    result = self.processor.convert_video_to_gif(
                        self.current_file, output_path, fps,
                        start_s=trim_start, end_s=trim_end,
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

    def run_full_pipeline(self, preset: str = None):
        """Stub: 1-click pipeline (IA + optimizar + fragmentar) — replaced by the PRO patch."""
        messagebox.showinfo(
            "WorkshopArt PRO",
            "El Pipeline 1-clic (IA + optimizar + fragmentar automatico) es una "
            "funcion exclusiva de la version PRO.\n\n"
            "Descarga el .exe compilado en:\n"
            "https://mxteoo7.itch.io/workshopart-pro"
        )

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



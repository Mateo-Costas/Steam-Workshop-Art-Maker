"""
_pro_features.py - Implementaciones PRO de WorkshopArt.

PRIVADO: este archivo esta gitignoreado. Solo existe en builds locales/PRO.
Se carga desde gui_methods.py al final del modulo para parchear los stubs.
"""
from __future__ import annotations
import sys
import uuid
import shutil
import threading
from pathlib import Path
from tkinter import messagebox
from PIL import Image, ImageEnhance


def process_full_ai(self):
    """Procesamiento completo con IA (Real-ESRGAN / Real-CUGAN)."""
    if not self.current_file:
        self._ui_warn("Advertencia", "Primero selecciona un archivo")
        return

    selected_model = self.model_var.get()
    if not selected_model:
        self._ui_warn("Advertencia", "Selecciona un modelo de IA")
        return

    def process():
        self._raise_if_cancelled()
        original_file = self.current_file
        processed_file = None
        temp_dir = None
        upscaled_frames = None

        try:
            def check_cancel():
                if self._cancel_event.is_set():
                    raise InterruptedError("Procesamiento cancelado por el usuario")

            self.update_status("Iniciando procesamiento con IA...", 5, "AI")
            self.log_message("=== PROCESAMIENTO CON IA ===", "INFO")
            self.log_message(f"Archivo: {self.current_file.name}")
            self.log_message(f"Modelo: {selected_model}")

            use_gpu = self.gpu_var.get()
            gpu_name = getattr(self, '_detected_gpu', None) or "GPU"
            mode = f"GPU ({gpu_name})" if use_gpu else "CPU"
            self.log_message(f"Modo de procesamiento: {mode}")

            check_cancel()

            if getattr(sys, 'frozen', False):
                base_temp = Path(sys.executable).parent / "SteamWorkshopAppData" / "temp"
            else:
                base_temp = Path("SteamWorkshopAppData/temp")

            unique_id = str(uuid.uuid4())[:8]
            temp_dir = base_temp / f"process_{unique_id}"
            temp_dir.mkdir(parents=True, exist_ok=True)

            frames_dir = temp_dir / "frames"
            upscaled_dir = temp_dir / "upscaled"
            frames_dir.mkdir(exist_ok=True)
            upscaled_dir.mkdir(exist_ok=True)

            self.update_status("Preparando archivo...", 10, "archivo")

            check_cancel()

            ext = self.current_file.suffix.lower()
            is_static_image = ext in ('.jpg', '.jpeg', '.png', '.bmp', '.webp')

            if ext in ('.mp4', '.avi', '.mov', '.mkv', '.webm', '.m4v', '.flv'):
                self.log_message("Convirtiendo video a GIF...")
                gif_path = self.current_file.with_suffix('.gif')
                gif_path = self.processor.convert_video_to_gif(self.current_file, gif_path, 24)
                if not gif_path:
                    raise Exception("Error convirtiendo video a GIF")
                self.current_file = gif_path
                self.log_message(f"Video convertido: {gif_path.name}")

            check_cancel()

            self.update_status("Extrayendo frames...", 20, "frames")
            self.log_message("Extrayendo frames...")

            if is_static_image:
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

            self.log_message(f"Frames extraidos: {len(frame_paths)}, FPS: {fps:.1f}")

            check_cancel()

            self.update_status(f"Aplicando IA con {mode}...", 40, "AI")

            def ai_progress(message, progress):
                if progress:
                    self.update_status(message, 40 + (progress * 0.4), "AI")
                self.log_message(message)

            upscaled_frames = self.processor.upscale_frames_batch(
                frames_dir, upscaled_dir, selected_model,
                use_gpu=use_gpu, progress_callback=ai_progress
            )

            if not upscaled_frames:
                raise Exception("Error en el upscaling con IA")

            self.log_message(f"IA aplicada: {len(upscaled_frames)} frames mejorados", "SUCCESS")

            check_cancel()

            if not isinstance(upscaled_frames, list) or len(upscaled_frames) == 0:
                raise Exception("Lista de frames upscaleados esta vacia")

            valid_frames = []
            for frame_path in upscaled_frames:
                if isinstance(frame_path, Path) and frame_path.exists():
                    valid_frames.append(frame_path)
                else:
                    self.log_message(f"Frame no valido: {frame_path}", "WARNING")

            if not valid_frames:
                raise Exception("No hay frames validos despues del upscaling")

            upscaled_frames = valid_frames
            self.log_message(f"Frames validos: {len(upscaled_frames)}")

            if self.enhance_colors_var.get():
                self.update_status("Preparando mejoras de color...", 85, "color")
                self.log_message("Mejoras de color se aplicaran al GIF final...")

            if is_static_image:
                self.update_status("Guardando imagen mejorada...", 90, "guardando")
                output_path = self.current_file.parent / f"{self.current_file.stem}_AI_4x.png"
                shutil.copy2(str(upscaled_frames[0]), str(output_path))

                if not output_path.exists():
                    raise Exception(f"Imagen no se guardo correctamente: {output_path}")

                file_size = output_path.stat().st_size
                self.log_message(f"Imagen mejorada: {file_size / (1024*1024):.2f} MB")

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
                self.update_status("Creando GIF final...", 90, "GIF")

                _ai_dir = self.processor._workspace_dir(self.current_file, "ai_x4")
                _ai_name = f"{self.current_file.stem}_AI_4x.gif"
                self.processor._archive_before_overwrite(_ai_dir, keep_names=[_ai_name])
                output_path = _ai_dir / _ai_name

                gif_created = self.processor.create_optimized_gif(upscaled_frames, output_path, int(fps))

                if not gif_created:
                    raise Exception("Error creando GIF optimizado")

                if not output_path.exists():
                    raise Exception(f"GIF no se creo correctamente: {output_path}")

                file_size = output_path.stat().st_size
                if file_size < 1024:
                    raise Exception(f"GIF creado esta corrupto (tamano: {file_size} bytes)")

                self.log_message(f"GIF base creado: {file_size / (1024*1024):.2f} MB")

                if self.enhance_colors_var.get():
                    try:
                        self.update_status("Aplicando mejoras de color...", 95, "color")
                        self.log_message("Aplicando mejoras de color...")

                        try:
                            with Image.open(output_path) as test_img:
                                if test_img.format != 'GIF':
                                    raise Exception(f"Archivo no es GIF valido: {test_img.format}")
                                frame_count = getattr(test_img, 'n_frames', 0)
                                if frame_count == 0:
                                    raise Exception("GIF no tiene frames validos")
                                self.log_message(f"GIF valido: {frame_count} frames")
                        except Exception as validation_error:
                            self.log_message(f"GIF no valido para mejoras: {validation_error}", "WARNING")
                            raise Exception(f"GIF base corrupto: {validation_error}")

                        enhanced_path = None
                        enhancement_error = None

                        def enhance_worker():
                            nonlocal enhanced_path, enhancement_error
                            try:
                                enhanced_path = self.processor.enhance_colors(
                                    output_path,
                                    self.contrast_var.get(),
                                    self.saturation_var.get(),
                                    vibrance=getattr(self, 'vibrance_var', None) and self.vibrance_var.get() or 0.0,
                                    sharpness=getattr(self, 'sharpness_var', None) and self.sharpness_var.get() or 0.0,
                                    temperature=getattr(self, 'temperature_var', None) and self.temperature_var.get() or 0.0,
                                )
                            except Exception as e:
                                enhancement_error = e

                        enhancement_thread = threading.Thread(target=enhance_worker, daemon=True)
                        enhancement_thread.start()
                        enhancement_thread.join(timeout=60)

                        if enhancement_thread.is_alive():
                            self.log_message("Timeout en mejoras de color (>60s)", "WARNING")
                            self.log_message("Continuando sin mejoras de color...", "INFO")
                        elif enhancement_error:
                            self.log_message(f"Error en mejoras: {enhancement_error}", "WARNING")
                            self.log_message("Continuando sin mejoras de color...", "INFO")
                        elif enhanced_path and enhanced_path != output_path and enhanced_path.exists():
                            enhanced_size = enhanced_path.stat().st_size / (1024*1024)
                            self.log_message(f"Mejoras aplicadas: {enhanced_size:.2f} MB", "SUCCESS")
                            output_path = enhanced_path
                        else:
                            self.log_message("No se requirieron mejoras de color", "INFO")

                    except Exception as color_error:
                        self.log_message(f"Saltando mejoras de color: {color_error}", "WARNING")

            processed_file = output_path
            self.current_file = output_path

            final_size = output_path.stat().st_size / (1024 * 1024)
            if final_size < 0.1:
                raise Exception(f"Archivo final muy pequeno: {final_size:.2f} MB")

            self.update_status("Procesamiento completado!", 100, "OK")

            def update_ui():
                self.show_file_info()
            self.update_queue.put((update_ui, ()))

            self.log_message("=== PROCESAMIENTO COMPLETADO ===", "SUCCESS")
            self.log_message(f"Archivo final: {output_path.name}")
            self.log_message(f"Tamano: {final_size:.2f} MB")

            try:
                self.processor._write_manifest(output_path.parent, "procesar_ai_x4",
                    {"modelo": selected_model, "modo": mode, "fps": int(fps),
                     "mejorar_colores": bool(self.enhance_colors_var.get()),
                     "contraste": self.contrast_var.get(),
                     "saturacion": self.saturation_var.get()},
                    archivos=[output_path], fuente=original_file)
            except Exception:
                pass

            try:
                self.log_message("Generando reporte de calidad...", "INFO")
                processing_details = {
                    "model": selected_model, "mode": mode,
                    "enhance_colors": self.enhance_colors_var.get(),
                    "contrast": self.contrast_var.get(),
                    "saturation": self.saturation_var.get()
                }
                if hasattr(self, 'quality_reporter') and self.quality_reporter:
                    quality_report = self.quality_reporter.create_quality_report(
                        original_file, processed_file, processing_details)
                    if quality_report:
                        self.log_message("Reporte de calidad generado", "SUCCESS")
                        self.root.after(1000, lambda: self.quality_reporter.show_quality_report_window(
                            quality_report, self.root))
                    else:
                        self.log_message("No se pudo generar reporte de calidad", "WARNING")
            except Exception as report_error:
                self.log_message(f"Error en reporte de calidad: {report_error}", "WARNING")

            self._ui_info("Exito!",
                f"Procesamiento completado exitosamente!\n\n"
                f"Archivo: {output_path.name}\n"
                f"Tamano: {final_size:.2f} MB\n"
                f"Modelo: {selected_model}\n"
                f"Procesado con: {mode}\n\n"
                f"Mejoras aplicadas: {'Si' if self.enhance_colors_var.get() else 'No'}\n"
                f"Se abrira el reporte de calidad...\n"
                f"Listo para fragmentar para Steam!")

        except InterruptedError:
            self.log_message("=== PROCESAMIENTO CANCELADO ===", "WARNING")
            self.update_status("Cancelado", 0, "cancelado")
            self._ui_info("Cancelado", "Procesamiento cancelado correctamente.")

        except Exception as e:
            self.log_message(f"ERROR CRITICO: {e}", "ERROR")
            self.update_status("Error", 0, "error")

            if "upscaled_frames" in str(e) or upscaled_frames is None:
                error_msg = (f"Error en procesamiento con IA:\n\n{e}\n\n"
                             "Posibles causas:\n"
                             "- Modelo de IA no disponible\n"
                             "- GPU no compatible\n"
                             "- Frames de entrada corruptos\n"
                             "- Memoria insuficiente\n\n"
                             "Soluciones:\n"
                             "- Verifica que el modelo este descargado\n"
                             "- Cambia a modo CPU\n"
                             "- Usa archivo mas pequeno\n"
                             "- Reinicia WorkshopArt")
            elif "GIF" in str(e) or "create_optimized_gif" in str(e):
                error_msg = (f"Error creando GIF final:\n\n{e}\n\n"
                             "Posibles causas:\n"
                             "- Frames de IA corruptos\n"
                             "- Memoria insuficiente\n"
                             "- Archivo original demasiado largo\n\n"
                             "Soluciones:\n"
                             "- Usar archivo mas corto (<10s)\n"
                             "- Cerrar otras aplicaciones\n"
                             "- Reiniciar WorkshopArt")
            else:
                error_msg = f"Error en procesamiento:\n\n{e}"

            self._ui_error("Error", error_msg)

        finally:
            try:
                if temp_dir and temp_dir.exists():
                    shutil.rmtree(temp_dir, ignore_errors=True)
                    self.log_message("Archivos temporales limpiados")
            except Exception as cleanup_error:
                self.log_message(f"Advertencia limpiando temporales: {cleanup_error}", "WARNING")
            self.update_status("Listo", 0, "OK")

    model_info = self.processor.model_manager.get_model_info(selected_model)
    gpu_name = getattr(self, '_detected_gpu', None) or "GPU"
    mode = f"GPU ({gpu_name})" if self.gpu_var.get() else "CPU"
    quality = "Alta" if self.quality_var.get() == "Alta Calidad" else "Balanceada"

    if messagebox.askyesno("Confirmar Procesamiento",
                           f"Procesar archivo con IA?\n\n"
                           f"Archivo: {self.current_file.name}\n"
                           f"Modelo: {model_info.get('name', selected_model)}\n"
                           f"Procesamiento: {mode}\n"
                           f"Calidad: {quality}\n"
                           f"Tiempo estimado: 2-10 minutos\n\n"
                           f"Mejoras de color: {'SI' if self.enhance_colors_var.get() else 'NO'}\n"
                           f"Se generara reporte de calidad\n\n"
                           f"Continuar?"):
        self._run_cancellable(process)


def enhance_animation(self):
    """Mejora de animacion con RIFE v4.6 (PRO)."""
    if not self.current_file:
        self._ui_warn("Advertencia", "Primero selecciona un archivo")
        return

    import subprocess as _sp
    import tempfile
    import platform as _pf

    _NO_WIN = {'creationflags': _sp.CREATE_NO_WINDOW} if _pf.system() == 'Windows' else {}

    # Locate rife exe
    if getattr(sys, 'frozen', False):
        base = Path(sys.executable).parent / "SteamWorkshopAppData"
    else:
        base = Path("SteamWorkshopAppData")

    rife_exe = base / "rife-ncnn-vulkan.exe"
    if not rife_exe.exists():
        messagebox.showerror(
            "RIFE no encontrado",
            f"No se encontro rife-ncnn-vulkan.exe en:\n{rife_exe}\n\n"
            "Reinicia la app para que se descargue automaticamente."
        )
        return

    # Choose model: prefer v4.6 then v4, then fallback
    rife_models_base = base / "rife"
    preferred = ["rife-v4.6", "rife-v4", "rife-v3.1", "rife-v3.0", "rife-HD"]
    model_dir = None
    for m in preferred:
        candidate = rife_models_base / m
        if candidate.exists():
            model_dir = candidate
            model_name = m
            break
    if model_dir is None:
        # Try rife models alongside exe
        for m in preferred:
            candidate = base.parent / m
            if candidate.exists():
                model_dir = candidate
                model_name = m
                break
    if model_dir is None:
        messagebox.showerror(
            "Modelos RIFE no encontrados",
            "No se encontraron modelos RIFE v4.6/v4.\n\n"
            "Reinstala la app para descargar los modelos."
        )
        return

    # Quality mode dialog
    import customtkinter as ctk
    dlg = ctk.CTkToplevel(self.root)
    dlg.title("Mejorar Animacion con RIFE")
    dlg.geometry("420x320")
    dlg.resizable(False, False)
    dlg.transient(self.root)
    dlg.grab_set()
    dlg.update_idletasks()
    dlg.geometry(f"+{self.root.winfo_x() + (self.root.winfo_width()-420)//2}"
                 f"+{self.root.winfo_y() + (self.root.winfo_height()-320)//2}")

    ctk.CTkLabel(dlg, text="Mejora de Animacion RIFE", font=("Segoe UI", 15, "bold")).pack(pady=(18, 4))
    ctk.CTkLabel(dlg, text=f"Modelo: {model_name}", font=("Segoe UI", 10),
                 text_color="#aaaaaa").pack(pady=(0, 12))

    tta_var = ctk.BooleanVar(value=False)
    multiply_var = ctk.StringVar(value="2")

    f1 = ctk.CTkFrame(dlg, fg_color="transparent")
    f1.pack(fill="x", padx=20, pady=4)
    ctk.CTkLabel(f1, text="Multiplicador de frames:", font=("Segoe UI", 11)).pack(side="left")
    ctk.CTkSegmentedButton(f1, values=["2", "4"], variable=multiply_var,
                           width=100).pack(side="right")

    f2 = ctk.CTkFrame(dlg, fg_color="transparent")
    f2.pack(fill="x", padx=20, pady=4)
    ctk.CTkSwitch(f2, text="Calidad maxima (TTA) — 4x mas lento",
                  variable=tta_var, font=("Segoe UI", 11)).pack(side="left")

    ctk.CTkLabel(dlg, text="TTA activa para cada frame 8 orientaciones,\nmejor resultado en movimiento complejo.",
                 font=("Segoe UI", 9), text_color="#666666").pack(pady=(4, 16))

    result = {"go": False}
    def _confirm():
        result["go"] = True
        dlg.destroy()

    bf = ctk.CTkFrame(dlg, fg_color="transparent")
    bf.pack(fill="x", padx=20)
    ctk.CTkButton(bf, text="Aplicar RIFE", command=_confirm,
                  fg_color="#e67e22", hover_color="#ca6f1e",
                  height=36, corner_radius=8, font=("Segoe UI", 12, "bold")).pack(side="left", padx=(0, 8))
    ctk.CTkButton(bf, text="Cancelar", command=dlg.destroy,
                  fg_color="transparent", border_width=1, border_color="#555",
                  height=36, corner_radius=8).pack(side="left")

    dlg.wait_window()
    if not result["go"]:
        return

    use_tta = tta_var.get()
    multiply = int(multiply_var.get())
    source_file = self.current_file

    def process():
        try:
            self.update_status("Extrayendo frames para RIFE...", 10, "RIFE")
            self.log_message("=== RIFE INTERPOLACION ===", "INFO")
            self.log_message(f"Modelo: {model_name}  Multiplicador: {multiply}x  TTA: {use_tta}")

            tmp = Path(tempfile.mkdtemp(prefix="wkart_rife_"))
            frames_in = tmp / "in"
            frames_out = tmp / "out"
            frames_in.mkdir()
            frames_out.mkdir()

            with Image.open(source_file) as img:
                duration = img.info.get("duration", 100) or 100
                orig_fps = 1000.0 / duration

            frame_paths, _ = self.processor.extract_gif_frames(source_file, frames_in)
            if not frame_paths:
                raise Exception("No se pudieron extraer frames")

            self.log_message(f"Frames extraidos: {len(frame_paths)}, FPS original: {orig_fps:.1f}")
            self.update_status("Interpolando con RIFE...", 40, "RIFE")

            cmd = [
                str(rife_exe),
                "-i", str(frames_in),
                "-o", str(frames_out),
                "-m", str(model_dir),
                "-n", str(len(frame_paths) * multiply),
                "-g", "0" if self.gpu_var.get() else "-1",
                "-f", "frame%08d.png",
                "-j", "1:2:1",
            ]
            if use_tta:
                cmd.append("-x")

            # Dynamic timeout: TTA multiplies per-frame cost ~4-8x; long GIFs at 4x
            # easily exceed a fixed 300 s.
            per_frame = 8 if use_tta else 2
            rife_timeout = max(300, len(frame_paths) * multiply * per_frame)
            r = _sp.run(cmd, capture_output=True, text=True, timeout=rife_timeout, **_NO_WIN)
            if r.returncode != 0:
                raise Exception(f"RIFE fallo (rc={r.returncode}): {r.stderr[:300]}")

            out_frames = sorted(frames_out.glob("*.png"))
            if not out_frames:
                raise Exception("RIFE no genero frames de salida")

            self.log_message(f"Frames interpolados: {len(out_frames)}")
            self.update_status("Ensamblando GIF interpolado...", 75, "GIF")

            new_fps = orig_fps * multiply
            out_dir = self.processor._workspace_dir(source_file, "interpolado")
            suffix = "_TTA" if use_tta else ""
            out_path = out_dir / f"{source_file.stem}_{model_name}_{multiply}x{suffix}.gif"

            created = self.processor.create_optimized_gif(out_frames, out_path, int(new_fps))
            if not created or not out_path.exists():
                raise Exception("Error creando GIF interpolado")

            import shutil as _sh
            _sh.rmtree(tmp, ignore_errors=True)

            size_mb = out_path.stat().st_size / (1024 * 1024)
            self.current_file = out_path
            self.update_status("RIFE completado!", 100, "OK")
            self.log_message(f"GIF interpolado: {out_path.name}  ({size_mb:.2f} MB)", "SUCCESS")
            self.root.after(0, self.show_file_info)
            self._ui_info("RIFE completado",
                f"Animacion mejorada con RIFE {model_name}\n\n"
                f"Frames: {len(frame_paths)} → {len(out_frames)}\n"
                f"FPS: {orig_fps:.1f} → {new_fps:.1f}\n"
                f"Archivo: {out_path.name}\n"
                f"Tamaño: {size_mb:.2f} MB")

        except Exception as e:
            self.log_message(f"ERROR RIFE: {e}", "ERROR")
            self.update_status("Error RIFE", 0, "error")
            self._ui_error("Error RIFE", str(e))
        finally:
            self.update_status("Listo", 0, "OK")

    self._run_cancellable(process)


def run_full_pipeline(self, preset: str = None):
    """Pipeline 1-clic (PRO): convertir -> IA -> colores -> fragmentar -> optimizar."""
    if not self.current_file:
        self._ui_warn("Advertencia", "Primero selecciona un archivo")
        return
    selected_model = self.model_var.get()
    if not selected_model:
        self._ui_warn("Advertencia", "Selecciona un modelo de IA")
        return
    preset = preset or "workshop_5part"

    if not messagebox.askyesno(
            "Pipeline 1-clic",
            f"Se ejecutara todo el flujo automaticamente:\n\n"
            f"Archivo: {self.current_file.name}\n"
            f"Modelo IA: {selected_model}\n"
            f"Preset: {preset}\n"
            f"Mejoras de color: {'SI' if self.enhance_colors_var.get() else 'NO'}\n\n"
            f"1) Convertir a GIF (si es video)\n"
            f"2) Upscale con IA\n"
            f"3) Mejoras de color\n"
            f"4) Fragmentar\n"
            f"5) Optimizar fragmentos a menos de 5 MB\n\n"
            f"Puede tardar varios minutos. Continuar?"):
        return

    def process():
        import tempfile
        work = self.current_file
        try:
            # 1) Video -> GIF
            if work.suffix.lower() in ('.mp4', '.avi', '.mov', '.mkv',
                                       '.webm', '.m4v', '.flv'):
                self.update_status("Pipeline 1/5: convirtiendo a GIF...", 5, "🎬")
                self.log_message("[Pipeline] Convirtiendo video a GIF...")
                conv_dir = self.processor._workspace_dir(work, "convertido")
                out = conv_dir / f"{work.stem}.gif"
                work = self.processor.convert_video_to_gif(work, out, 24)
                if not work:
                    raise Exception("Fallo la conversion a GIF")
            self._raise_if_cancelled()

            # 2) AI upscale
            self.update_status("Pipeline 2/5: upscale con IA...", 20, "🤖")
            self.log_message(f"[Pipeline] Upscale IA con {selected_model}...")
            tmp = Path(tempfile.mkdtemp(prefix="wkart_pipe_"))
            frames_in, frames_out = tmp / "in", tmp / "out"
            frames_in.mkdir(), frames_out.mkdir()
            is_static = work.suffix.lower() in ('.jpg', '.jpeg', '.png',
                                                '.bmp', '.webp')
            try:
                if is_static:
                    with Image.open(work) as img:
                        img.convert('RGB').save(frames_in / "frame_000000.png")
                    fps = 1
                else:
                    _paths, duration = self.processor.extract_gif_frames(work, frames_in)
                    if not _paths:
                        raise Exception("No se pudieron extraer frames")
                    fps = 1000 / duration if duration else 24

                def ai_progress(msg, pct):
                    if pct:
                        self.update_status(msg, 20 + pct * 0.3, "🤖")

                upscaled = self.processor.upscale_frames_batch(
                    frames_in, frames_out, selected_model,
                    use_gpu=self.gpu_var.get(), progress_callback=ai_progress)
                if not upscaled:
                    raise Exception("Fallo el upscale con IA")
                self._raise_if_cancelled()

                ai_dir = self.processor._workspace_dir(work, "ai_x4")
                if is_static:
                    ai_out = ai_dir / f"{work.stem}_AI_4x.png"
                    shutil.copy2(str(upscaled[0]), str(ai_out))
                else:
                    ai_out = ai_dir / f"{work.stem}_AI_4x.gif"
                    if not self.processor.create_optimized_gif(
                            upscaled, ai_out, int(fps)):
                        raise Exception("Fallo creando el GIF upscaleado")
                work = ai_out
            finally:
                shutil.rmtree(tmp, ignore_errors=True)

            # 3) Color enhancement (optional)
            if self.enhance_colors_var.get():
                self.update_status("Pipeline 3/5: mejoras de color...", 55, "🎨")
                self.log_message("[Pipeline] Aplicando mejoras de color...")
                enhanced = self.processor.enhance_colors(
                    work, self.contrast_var.get(), self.saturation_var.get(),
                    vibrance=self.vibrance_var.get(),
                    sharpness=self.sharpness_var.get(),
                    temperature=self.temperature_var.get())
                if enhanced and enhanced.exists():
                    work = enhanced
            self._raise_if_cancelled()

            # 4) Fragment with the chosen preset
            self.update_status("Pipeline 4/5: fragmentando...", 70, "✂️")
            self.log_message(f"[Pipeline] Fragmentando preset '{preset}'...")
            if preset == "workshop_5part":
                ok = self.processor.split_gif_for_steam(work)
            elif preset == "artwork_2part" and not is_static:
                ok = self.processor.split_gif_for_artwork_showcase(work)
            elif preset == "artwork_2part":
                ok = self.processor.split_image_for_artwork_showcase(work)
            elif is_static:
                ok = self.processor.split_image_for_showcase(work, preset)
            else:
                ok = self.processor.split_gif_for_showcase(work, preset)
            if not ok:
                raise Exception("Fallo la fragmentacion")
            self._raise_if_cancelled()

            # 5) Batch-optimise oversized GIF fragments
            frag_dir = self.processor.get_fragments_dir(work)
            fragments = sorted(p for p in frag_dir.iterdir() if p.is_file()
                               and p.suffix.lower() == ".gif")
            oversized = [p for p in fragments
                         if p.stat().st_size > 5 * 1024 * 1024]
            if oversized:
                self.update_status("Pipeline 5/5: optimizando fragmentos...", 85, "🎯")
                self.log_message(f"[Pipeline] Optimizando {len(oversized)} fragmentos > 5 MB...")
                self.processor.shrink_batch_to_size_cap(
                    fragments, max_mb=5.0, min_mb=4.7,
                    progress_cb=lambda m: self.log_message(f"   {m}"))

            self.current_file = work
            self.update_queue.put((self.show_file_info, ()))
            self.update_status("Pipeline completado!", 100, "✅")
            self.log_message("[Pipeline] COMPLETADO", "SUCCESS")
            total = sum(p.stat().st_size for p in frag_dir.iterdir()
                        if p.is_file()) / (1024 * 1024)
            self._ui_info(
                "Pipeline completado",
                f"Flujo completo terminado.\n\n"
                f"Archivo final: {work.name}\n"
                f"Fragmentos en: {frag_dir}\n"
                f"Tamano total: {total:.2f} MB\n\n"
                f"Revisa el paso 4 (Subir) para publicarlos.")
        except InterruptedError:
            raise
        except Exception as e:
            self.update_status("Error en pipeline", 0, "❌")
            self.log_message(f"[Pipeline] ERROR: {e}", "ERROR")
            self._ui_error("Error en pipeline", str(e))
        finally:
            self.update_status("Listo", 0, "✅")

    self._run_cancellable(process)


def validate_steam_profile(self):
    """Validador de perfil Steam (PRO): existencia, visibilidad y nivel."""
    import re
    import urllib.request
    import customtkinter as ctk
    from fragment_preview import _ProfileFetcher

    dlg = ctk.CTkToplevel(self.root)
    dlg.title("Validar perfil Steam")
    dlg.geometry("440x260")
    dlg.transient(self.root)
    dlg.grab_set()

    ctk.CTkLabel(dlg, text="Validador de perfil Steam",
                 font=("Segoe UI", 14, "bold")).pack(pady=(16, 4))
    ctk.CTkLabel(dlg, text="Tu vanity name o URL completa del perfil:",
                 font=("Segoe UI", 10), text_color="#aaa").pack()

    entry_var = ctk.StringVar(value=self.config.get("ui.steam_vanity", ""))
    ctk.CTkEntry(dlg, textvariable=entry_var, width=340).pack(pady=8)

    result_label = ctk.CTkLabel(dlg, text="", font=("Segoe UI", 10),
                                justify="left", wraplength=390)
    result_label.pack(pady=4, padx=16)

    def _set_result(text, color="#adbac7"):
        self.update_queue.put(
            (lambda: result_label.winfo_exists()
             and result_label.configure(text=text, text_color=color), ()))

    def _validate():
        raw = entry_var.get().strip()
        if not raw:
            return
        self.config.set("ui.steam_vanity", raw)
        url = raw if raw.startswith("http") \
            else f"https://steamcommunity.com/id/{raw}"

        def worker():
            try:
                _set_result("Consultando Steam...")
                data = _ProfileFetcher().fetch(url, lambda _m: None)
                lines = [f"✅ Perfil encontrado: {data['name']}",
                         f"{'🟢 Online' if data['online'] else '⚪ Offline'}"]
                # Best-effort level scrape from the public profile HTML.
                level = None
                try:
                    req = urllib.request.Request(
                        url, headers=_ProfileFetcher._HEADERS)
                    with urllib.request.urlopen(req, timeout=12) as r:
                        html = r.read().decode("utf-8", errors="replace")
                    m = re.search(
                        r'friendPlayerLevelNum">\s*(\d+)', html)
                    if m:
                        level = int(m.group(1))
                except Exception:
                    pass
                if level is not None:
                    if level >= 10:
                        lines.append(f"✅ Nivel {level}: puedes usar showcases")
                        color = "#3fb950"
                    else:
                        lines.append(f"⚠️ Nivel {level}: los showcases requieren nivel 10+")
                        color = "#d29922"
                else:
                    lines.append("ℹ️ Nivel no detectable (recuerda: showcases requieren nivel 10+)")
                    color = "#adbac7"
                _set_result("\n".join(lines), color)
            except Exception as e:
                _set_result(f"❌ {e}", "#f85149")

        threading.Thread(target=worker, daemon=True).start()

    ctk.CTkButton(dlg, text="Validar", command=_validate,
                  fg_color="#58a6ff", height=34).pack(pady=8)


def export_steam_pack(self):
    """Export ZIP (PRO): fragmentos + README con instrucciones y snippets JS."""
    import zipfile

    if not self.current_file:
        self._ui_warn("Advertencia", "Primero selecciona un archivo")
        return
    frag_dir = self.processor.get_fragments_dir(self.current_file)
    fragments = []
    if frag_dir.exists():
        fragments = sorted(p for p in frag_dir.iterdir() if p.is_file()
                           and p.suffix.lower() in {".gif", ".jpg", ".jpeg", ".png"})
    if not fragments:
        self._ui_warn("Sin fragmentos",
                      "No hay fragmentos para exportar. Fragmenta primero (paso 3).")
        return

    readme = (
        "WorkshopArt - Steam pack\n"
        "============================\n\n"
        f"Fragmentos incluidos: {len(fragments)}\n\n"
        "COMO SUBIRLOS A STEAM\n"
        "1. Abre https://steamcommunity.com/sharedfiles/edititem/767/3/\n"
        "2. Abre la consola del navegador (F12 -> Console).\n"
        "3. Pega el snippet correspondiente y pulsa Enter:\n\n"
        "   Workshop (GIF animado de perfil):\n"
        "   $J('[name=consumer_app_id]').val(480);\n"
        "   $J('[name=file_type]').val(0);\n"
        "   $J('[name=visibility]').val(0);\n\n"
        "   Artwork showcase:\n"
        "   $J('[name=consumer_app_id]').val(767);\n"
        "   $J('[name=file_type]').val(3);\n"
        "   $J('[name=visibility]').val(0);\n\n"
        "4. Sube cada fragmento en orden, ponle titulo y guarda.\n"
        "5. En tu perfil: Editar perfil -> Showcase -> asigna cada pieza.\n\n"
        "Requisito: cuenta Steam nivel 10+ para los showcases.\n"
    )

    zip_path = frag_dir / f"{self.current_file.stem}_steam_pack.zip"
    try:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for frag in fragments:
                zf.write(frag, frag.name)
            zf.writestr("LEEME.txt", readme)
        self.log_message(f"Steam pack exportado: {zip_path.name}", "SUCCESS")
        self._ui_info("Export completado",
                      f"ZIP creado con {len(fragments)} fragmentos:\n\n{zip_path}")
    except Exception as e:
        self._ui_error("Error exportando", str(e))


def fragment_workshop_flow(self):
    """Flujo de fragmentacion Workshop con preview (PRO)."""
    show_preview = messagebox.askyesno(
        "Opciones de Fragmentacion",
        f"Como quieres fragmentar {self.current_file.name}?\n\n"
        f"SI: Ver preview primero\n"
        f"NO: Fragmentar directamente\n\n"
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

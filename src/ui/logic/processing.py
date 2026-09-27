"""ui.logic.processing - AI upscaling, color enhancement, video->GIF and RIFE."""
import shutil
import tkinter as tk
from pathlib import Path
from tkinter import messagebox

import customtkinter as ctk
from PIL import Image

from app_paths import APP_DIR, RIFE_DIR, find_tool, make_temp_dir
from gif_utils import MAX_GIF_FPS
from i18n import t
from processing.common import run_tool, tail
from ui import theme
from ui.logic.common import IMAGE_EXTS, VIDEO_EXTS
from ui.theme import Colors
from video_utils import probe_video

#: RIFE model folders, best first (searched in SteamWorkshopAppData/rife and the app folder).
_RIFE_MODELS = ("rife-v4.6", "rife-v4", "rife-v3.1", "rife-v3.0", "rife-HD")


class ProcessingMixin:
    """AI upscaling, color adjustments, MP4->GIF conversion and RIFE interpolation."""

    def _require_file(self) -> bool:
        if not self.current_file:
            self._ui_warn(t("warning_title", fallback="Aviso"),
                          t("select_file_first", fallback="Primero selecciona un archivo"))
            return False
        return True

    # ------------------------------------------------------------------
    # AI upscaling
    # ------------------------------------------------------------------
    def _ai_upscale(self, source: Path, model_id: str, use_gpu: bool,
                    progress_range=(10, 80)) -> Path:
        """Upscale a GIF, video or image with the selected model; return the new file.

        Animated results keep the source timing and are limited to the Steam
        profile width (they are an intermediate step before fragmenting).
        """
        low, high = progress_range

        def ai_progress(message, percent):
            if percent:
                self.update_status(message, low + (high - low) * percent / 100, "🤖")

        work = make_temp_dir("wkart_ai_")
        try:
            frames_in, frames_out = work / "in", work / "out"
            frames_in.mkdir()
            static = source.suffix.lower() in IMAGE_EXTS
            if static:
                with Image.open(source) as img:
                    img.convert("RGB").save(frames_in / "frame_000001.png")
                fps = 1.0
            else:
                # The result is capped at the Steam profile width, so larger
                # frames would only make the AI slower; videos go at 24 fps.
                self.update_status(t("status_extracting", fallback="Extrayendo frames..."), low, "🎞️")
                frames, fps = self.processor.extract_gif_frames(
                    source, frames_in, max_fps=24 if source.suffix.lower() in VIDEO_EXTS else 50,
                    max_width=int(self.config.get("steam_profile.width", 638)))
                if not frames:
                    raise RuntimeError(t("err_extract_frames", fallback="No se pudieron extraer los frames"))
                self.log_message(f"Frames extraidos: {len(frames)} a {fps:.2f} fps")
            self._raise_if_cancelled()

            upscaled = self.processor.upscale_frames_batch(frames_in, frames_out, model_id,
                                                           use_gpu=use_gpu,
                                                           progress_callback=ai_progress)
            if not upscaled:
                raise RuntimeError(t("err_ai_failed",
                                     fallback="El procesamiento con IA ha fallado. Prueba con otro "
                                              "modelo o desactiva la GPU."))
            self._raise_if_cancelled()

            out_dir = self.processor._workspace_dir(source, "ai")
            if static:
                output = out_dir / f"{source.stem}_AI.png"
                shutil.copyfile(upscaled[0], output)
            else:
                output = out_dir / f"{source.stem}_AI.gif"
                self.update_status(t("status_building_gif", fallback="Creando GIF..."), high, "🎞️")
                if not self.processor.create_optimized_gif(upscaled, output, fps):
                    raise RuntimeError(t("err_build_gif", fallback="No se pudo crear el GIF"))
            return output
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def process_full_ai(self):
        """AI upscale of the current file, then the color adjustments if enabled."""
        if not self._require_file():
            return
        model_id = self.selected_model_id()
        if not model_id:
            self._ui_warn(t("warning_title", fallback="Aviso"),
                          t("select_model_first",
                            fallback="No hay modelos de IA. Usa 'Descargar modelos' primero."))
            return
        use_gpu = self.gpu_var.get()
        enhance = self.enhance_colors_var.get()
        mode = f"GPU ({getattr(self, '_detected_gpu', None) or 'GPU'})" if use_gpu else "CPU"
        info = self.processor.model_manager.get_model_info(model_id)
        if not messagebox.askyesno(
                t("process_ai", fallback="Procesar con IA"),
                t("confirm_ai", fallback="¿Procesar con IA?\n\nArchivo: {file}\nModelo: {model}\n"
                                         "Modo: {mode}\nMejorar colores: {colors}\n\n"
                                         "Puede tardar varios minutos.",
                  file=self.current_file.name, model=info.get("name", model_id), mode=mode,
                  colors=t("yes", fallback="Sí") if enhance else t("no", fallback="No")),
                parent=self.root):
            return
        source = self.current_file
        adjust = self._color_values()

        def process():
            self.log_message(f"=== IA: {source.name} con {model_id} ({mode}) ===")
            output = self._ai_upscale(source, model_id, use_gpu)
            if enhance:
                self.update_status(t("status_colors", fallback="Mejorando colores..."), 90, "🎨")
                output = self.processor.enhance_colors(output, **adjust)
            self.current_file = output
            self.update_queue.put((self.show_file_info, ()))
            size_mb = output.stat().st_size / 1048576
            self.update_status(t("status_done", fallback="Completado"), 100, "✅")
            self.log_message(f"Resultado: {output} ({size_mb:.2f} MB)", "SUCCESS")
            self._show_quality_report(source, output, {"model": model_id, "mode": mode,
                                                       "enhance_colors": enhance, **adjust})
            self._ui_info(t("process_ai", fallback="Procesar con IA"),
                          t("ai_done", fallback="Procesamiento completado.\n\nArchivo: {file}\n"
                                                "Tamaño: {mb:.2f} MB\n\nYa puedes fragmentarlo en el paso 3.",
                            file=output.name, mb=size_mb))

        self._run_cancellable(process, t("process_ai", fallback="Procesar con IA"))

    def _show_quality_report(self, original: Path, processed: Path, details: dict) -> None:
        try:
            report = self.quality_reporter.create_quality_report(original, processed, details)
        except Exception as e:
            self.log_message(f"No se pudo generar el reporte de calidad: {e}", "WARNING")
            return
        if report:
            self.update_queue.put((lambda: self.quality_reporter.show_quality_report_window(
                report, self.root), ()))

    # ------------------------------------------------------------------
    # Color adjustments
    # ------------------------------------------------------------------
    def _color_values(self) -> dict:
        return dict(contrast=self.contrast_var.get(), saturation=self.saturation_var.get(),
                    vibrance=self.vibrance_var.get(), sharpness=self.sharpness_var.get(),
                    temperature=self.temperature_var.get())

    def enhance_colors_only(self):
        """Apply the color sliders to the current GIF or image (no AI)."""
        if not self._require_file():
            return
        if self.current_file.suffix.lower() in VIDEO_EXTS:
            self._ui_warn(t("colors_only", fallback="Solo colores"),
                          t("colors_need_gif", fallback="Convierte primero el video a GIF (botón Video → GIF)."))
            return
        source, adjust = self.current_file, self._color_values()

        def process():
            self.update_status(t("status_colors", fallback="Mejorando colores..."), 50, "🎨")
            self.log_message(f"Ajustes de color: {adjust}")
            result = self.processor.enhance_colors(source, **adjust)
            if result == source:
                raise RuntimeError(t("err_colors", fallback="No se pudieron aplicar los ajustes de "
                                                            "color. Revisa el log de proceso."))
            self.current_file = result
            self.update_queue.put((self.show_file_info, ()))
            self.update_status(t("status_done", fallback="Completado"), 100, "✅")
            self.log_message(f"Colores aplicados: {result}", "SUCCESS")

        self._run_cancellable(process, t("colors_only", fallback="Solo colores"))

    # ------------------------------------------------------------------
    # Video -> GIF
    # ------------------------------------------------------------------
    def convert_mp4_to_gif(self):
        """Dialog to convert the current video to GIF (fps, trim, size)."""
        if not self._require_file():
            return
        source = self.current_file
        if source.suffix.lower() not in VIDEO_EXTS:
            self._ui_warn(t("mp4_to_gif", fallback="Video → GIF"),
                          t("not_a_video", fallback="El archivo seleccionado no es un video."))
            return
        try:
            info = probe_video(source)
        except ValueError as e:
            self._ui_error(t("mp4_to_gif", fallback="Video → GIF"), str(e))
            return
        duration = max(0.5, info.duration or 10.0)
        steam_width = int(self.config.get("steam_profile.width", 638))

        dlg = ctk.CTkToplevel(self.root)
        dlg.title(t("convert_title", fallback="Convertir video a GIF"))
        dlg.geometry("480x560")
        dlg.transient(self.root)
        dlg.after(50, dlg.grab_set)

        body = ctk.CTkScrollableFrame(dlg, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=20, pady=(16, 8))

        def heading(text):
            ctk.CTkLabel(body, text=text, font=theme.font("SUBHEADING"),
                         text_color=Colors.TEXT).pack(anchor="w", pady=(12, 4))

        ctk.CTkLabel(body, text=source.name, font=theme.font("SUBHEADING"),
                     text_color=Colors.ACCENT, wraplength=420).pack(anchor="w")
        ctk.CTkLabel(body, text=f"{info.width}x{info.height} · {info.fps:.1f} FPS · {duration:.1f} s",
                     font=theme.font("CAPTION"), text_color=Colors.TEXT_SECONDARY).pack(anchor="w")

        heading(t("gif_fps", fallback="FPS del GIF"))
        fps_var = tk.StringVar(value=str(min(24, max(1, round(info.fps or 24)))))
        row = ctk.CTkFrame(body, fg_color="transparent")
        row.pack(fill="x")
        for option in (12, 15, 20, 24, 30):
            ctk.CTkRadioButton(row, text=str(option), variable=fps_var, value=str(option),
                               font=theme.font("SMALL"), radiobutton_width=16,
                               radiobutton_height=16).pack(side="left", padx=(0, 10))
        custom = ctk.CTkFrame(body, fg_color="transparent")
        custom.pack(fill="x", pady=(6, 0))
        ctk.CTkLabel(custom, text=t("custom_fps", fallback="Otro valor (1-50):"),
                     font=theme.font("SMALL")).pack(side="left")
        ctk.CTkEntry(custom, textvariable=fps_var, width=60, height=28).pack(side="left", padx=8)

        heading(t("trim", fallback="Recorte"))
        start_var, end_var = tk.DoubleVar(value=0.0), tk.DoubleVar(value=duration)
        trim_label = ctk.CTkLabel(body, text="", font=theme.font("CAPTION"),
                                  text_color=Colors.TEXT_SECONDARY)
        ctk.CTkSlider(body, from_=0.0, to=duration, variable=start_var).pack(fill="x", pady=2)
        ctk.CTkSlider(body, from_=0.0, to=duration, variable=end_var).pack(fill="x", pady=2)
        trim_label.pack(anchor="w")

        heading(t("gif_size", fallback="Tamaño"))
        shrink_var = tk.BooleanVar(value=True)
        ctk.CTkCheckBox(body, text=t("shrink_to_steam", fallback="Reducir a {w} px de ancho (Steam)",
                                     w=steam_width),
                        variable=shrink_var, font=theme.font("SMALL"),
                        checkbox_width=18, checkbox_height=18).pack(anchor="w")
        ctk.CTkLabel(body, text=t("shrink_hint", fallback="Desmárcalo para conservar la resolución "
                                                          "original (útil para Panorama)."),
                     font=theme.font("CAPTION"), text_color=Colors.TEXT_MUTED,
                     wraplength=420, justify="left").pack(anchor="w")
        enhance_var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(body, text=t("apply_color_sliders",
                                     fallback="Aplicar también los ajustes de color del paso 2"),
                        variable=enhance_var, font=theme.font("SMALL"),
                        checkbox_width=18, checkbox_height=18).pack(anchor="w", pady=(8, 0))

        estimate = ctk.CTkLabel(body, text="", font=theme.font("CAPTION"), text_color=Colors.TEXT_MUTED)
        estimate.pack(anchor="w", pady=(10, 0))

        def read_fps():
            try:
                return max(1, min(int(MAX_GIF_FPS), int(float(fps_var.get()))))
            except (ValueError, tk.TclError):
                return None

        def refresh(*_):
            start, end = start_var.get(), end_var.get()
            if end - start < 0.5:
                end = min(duration, start + 0.5)
                end_var.set(end)
            trim_label.configure(text=t("trim_range", fallback="De {a:.1f} s a {b:.1f} s → {d:.1f} s de GIF",
                                        a=start, b=end, d=end - start))
            fps = read_fps()
            if fps is None:
                estimate.configure(text=t("invalid_fps", fallback="FPS no válido"))
                return
            width = steam_width if shrink_var.get() else info.width
            scale = (min(width, info.width) / steam_width) ** 2
            size_mb = (end - start) * fps * 0.02 * scale  # rough: ~20 KB per 638-px frame
            estimate.configure(text=t("size_estimate", fallback="Tamaño estimado: ~{mb:.1f} MB", mb=size_mb))

        for var in (fps_var, start_var, end_var, shrink_var):
            var.trace_add("write", refresh)
        refresh()

        def start_conversion():
            fps = read_fps()
            if fps is None:
                messagebox.showwarning(t("gif_fps", fallback="FPS del GIF"),
                                       t("invalid_fps", fallback="FPS no válido"), parent=dlg)
                return
            start = start_var.get() if start_var.get() > 0.05 else None
            end = end_var.get() if end_var.get() < duration - 0.05 else None
            max_width = steam_width if shrink_var.get() else 1920
            apply_colors, adjust = enhance_var.get(), self._color_values()
            dlg.destroy()

            def process():
                self.update_status(t("status_converting", fallback="Convirtiendo video a GIF..."), 20, "🎬")
                out_dir = self.processor._workspace_dir(source, "convertido")
                output = out_dir / f"{source.stem}.gif"
                self.processor._archive_before_overwrite(out_dir, keep_names=[output.name],
                                                         protect=source)
                result = self.processor.convert_video_to_gif(source, output, fps, start_s=start,
                                                             end_s=end, max_width=max_width)
                if not result:
                    raise RuntimeError(t("err_convert", fallback="No se pudo convertir el video. "
                                                                 "Revisa el log de proceso."))
                if apply_colors:
                    self.update_status(t("status_colors", fallback="Mejorando colores..."), 80, "🎨")
                    result = self.processor.enhance_colors(result, **adjust)
                self.processor._write_manifest(out_dir, "convertir_video_a_gif",
                                               {"fps": fps, "inicio": start, "fin": end,
                                                "ancho_max": max_width, "colores": apply_colors},
                                               archivos=[result], fuente=source)
                self.current_file = result
                self.update_queue.put((self.show_file_info, ()))
                size_mb = result.stat().st_size / 1048576
                self.update_status(t("status_done", fallback="Completado"), 100, "✅")
                self.log_message(f"GIF creado: {result} ({size_mb:.2f} MB)", "SUCCESS")

            self._run_cancellable(process, t("mp4_to_gif", fallback="Video → GIF"))

        buttons = ctk.CTkFrame(dlg, fg_color="transparent")
        buttons.pack(fill="x", padx=20, pady=(0, 16))
        ctk.CTkButton(buttons, text=t("convert_btn", fallback="Convertir a GIF"), command=start_conversion,
                      fg_color=Colors.ACCENT, hover_color=Colors.ACCENT_DARK,
                      height=34, corner_radius=8).pack(side="right", padx=(10, 0))
        ctk.CTkButton(buttons, text=t("cancel_btn", fallback="Cancelar"), command=dlg.destroy,
                      fg_color="transparent", border_width=1, border_color=Colors.BORDER,
                      hover_color=Colors.HOVER, height=34, corner_radius=8).pack(side="right")

    # ------------------------------------------------------------------
    # RIFE frame interpolation
    # ------------------------------------------------------------------
    @staticmethod
    def _find_rife_model():
        for name in _RIFE_MODELS:
            for base in (RIFE_DIR, APP_DIR):
                if (base / name).is_dir():
                    return name, base / name
        return None, None

    def enhance_animation(self):
        """Smooth the animation with RIFE frame interpolation (2x or 4x frames)."""
        if not self._require_file():
            return
        source = self.current_file
        if source.suffix.lower() in IMAGE_EXTS:
            self._ui_warn(t("enhance_animation", fallback="Mejorar animación"),
                          t("rife_needs_animation", fallback="RIFE necesita un GIF o un video."))
            return
        rife_exe = find_tool("rife-ncnn-vulkan")
        model_name, model_dir = self._find_rife_model()
        if not rife_exe or not model_dir:
            self._ui_error(t("enhance_animation", fallback="Mejorar animación"),
                           t("rife_missing", fallback="RIFE no está instalado. Reinicia la aplicación "
                                                      "para que se descargue automáticamente."))
            return

        dlg = ctk.CTkToplevel(self.root)
        dlg.title(t("enhance_animation", fallback="Mejorar animación"))
        dlg.geometry("440x300")
        dlg.resizable(False, False)
        dlg.transient(self.root)
        dlg.after(50, dlg.grab_set)
        ctk.CTkLabel(dlg, text=f"RIFE · {model_name}", font=theme.font("HEADING")).pack(pady=(18, 10))
        multiply_var = ctk.StringVar(value="2")
        row = ctk.CTkFrame(dlg, fg_color="transparent")
        row.pack(fill="x", padx=20, pady=4)
        ctk.CTkLabel(row, text=t("rife_multiplier", fallback="Multiplicar frames:"),
                     font=theme.font("SMALL")).pack(side="left")
        ctk.CTkSegmentedButton(row, values=["2", "4"], variable=multiply_var, width=100).pack(side="right")
        tta_var = ctk.BooleanVar(value=False)
        ctk.CTkSwitch(dlg, text=t("rife_tta", fallback="Calidad máxima (TTA), unas 4 veces más lento"),
                      variable=tta_var, font=theme.font("SMALL")).pack(anchor="w", padx=20, pady=6)
        ctk.CTkLabel(dlg, text=t("rife_fps_note", fallback="Los GIF no pasan de 50 FPS: si el resultado "
                                                            "los supera se ajusta sin cambiar la velocidad."),
                     font=theme.font("CAPTION"), text_color=Colors.TEXT_MUTED,
                     wraplength=390, justify="left").pack(padx=20, pady=(4, 12))
        chosen = {"go": False}

        def confirm():
            chosen["go"] = True
            dlg.destroy()

        buttons = ctk.CTkFrame(dlg, fg_color="transparent")
        buttons.pack(fill="x", padx=20)
        ctk.CTkButton(buttons, text=t("apply_rife", fallback="Aplicar RIFE"), command=confirm,
                      fg_color="#e67e22", hover_color="#ca6f1e", height=36,
                      corner_radius=8).pack(side="left", padx=(0, 8))
        ctk.CTkButton(buttons, text=t("cancel_btn", fallback="Cancelar"), command=dlg.destroy,
                      fg_color="transparent", border_width=1, border_color=Colors.BORDER,
                      height=36, corner_radius=8).pack(side="left")
        dlg.wait_window()
        if not chosen["go"]:
            return
        multiply, use_tta, use_gpu = int(multiply_var.get()), tta_var.get(), self.gpu_var.get()

        def process():
            work = make_temp_dir("wkart_rife_")
            try:
                frames_in, frames_out = work / "in", work / "out"
                frames_out.mkdir(parents=True)
                self.update_status(t("status_extracting", fallback="Extrayendo frames..."), 10, "🎞️")
                frames, fps = self.processor.extract_gif_frames(
                    source, frames_in, max_width=int(self.config.get("steam_profile.width", 638)))
                if not frames:
                    raise RuntimeError(t("err_extract_frames", fallback="No se pudieron extraer los frames"))
                self._raise_if_cancelled()
                self.update_status(t("status_rife", fallback="Interpolando con RIFE..."), 40, "✨")
                cmd = [rife_exe, "-i", frames_in, "-o", frames_out, "-m", model_dir,
                       "-n", str(len(frames) * multiply), "-g", "0" if use_gpu else "-1",
                       "-f", "frame%08d.png", "-j", "1:2:1"]
                if use_tta:
                    cmd.append("-x")
                timeout = max(300, len(frames) * multiply * (8 if use_tta else 2))
                result = run_tool(cmd, timeout=timeout)
                out_frames = sorted(frames_out.glob("*.png"))
                if result.returncode != 0 or not out_frames:
                    raise RuntimeError(f"RIFE: {tail(result.stderr, 300)}")
                self._raise_if_cancelled()

                self.update_status(t("status_building_gif", fallback="Creando GIF..."), 80, "🎞️")
                out_dir = self.processor._workspace_dir(source, "interpolado")
                output = out_dir / f"{source.stem}_rife_{multiply}x{'_tta' if use_tta else ''}.gif"
                new_fps = fps * multiply
                if not self.processor.create_optimized_gif(out_frames, output, new_fps):
                    raise RuntimeError(t("err_build_gif", fallback="No se pudo crear el GIF"))
                self.current_file = output
                self.update_queue.put((self.show_file_info, ()))
                self.update_status(t("status_done", fallback="Completado"), 100, "✅")
                self.log_message(f"RIFE: {len(frames)} -> {len(out_frames)} frames, "
                                 f"{fps:.1f} -> {min(new_fps, MAX_GIF_FPS):.1f} fps: {output}", "SUCCESS")
            finally:
                shutil.rmtree(work, ignore_errors=True)

        self._run_cancellable(process, t("enhance_animation", fallback="Mejorar animación"))

    def _open_fragment_preview(self, preset: str = None):
        """Open the fragment layout preview for the current file."""
        if not self._require_file():
            return
        try:
            self.fragment_previewer.create_fragment_preview(self.current_file, self.root,
                                                            preset=preset)
        except Exception as e:
            self._ui_error(t("open_preview", fallback="Preview de fragmentos"), str(e))

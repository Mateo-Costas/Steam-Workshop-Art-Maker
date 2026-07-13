"""ui.logic.fragmentation - Steam fragmentation flows, size optimisation, result dialogs."""
import os
import shutil
import subprocess
import webbrowser
from pathlib import Path
from typing import Optional

import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk, ImageSequence

from theme_PRO import Colors, Fonts
from ui.logic.common import _NO_WINDOW_FLAGS, _STATIC_IMAGE_EXTS


class FragmentationMixin:
    """Fragmentation presets, quality/size optimisation and result dialogs."""

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
# ImportError branch is the normal code path for public-repo users.
# ---------------------------------------------------------------------------


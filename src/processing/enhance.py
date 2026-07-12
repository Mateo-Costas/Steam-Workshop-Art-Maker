"""processing.enhance - color enhancement, 60fps interpolation, motion blur."""
import shutil
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image, ImageSequence, ImageEnhance, ImageFilter
from tqdm import tqdm

from processing.common import logger


class EnhanceMixin:
    
    # ------------------------------------------------------------------
    # Color helpers (vibrance, sharpness, temperature)
    # ------------------------------------------------------------------

    @staticmethod
    def _apply_vibrance(img: Image.Image, amount: float) -> Image.Image:
        """Boost under-saturated pixels more than already-vivid ones (amount 0..1).
        Unlike uniform saturation, vibrance protects already-vivid colours from clipping."""
        if amount == 0:
            return img
        arr = np.array(img.convert("RGB"), dtype=np.float32) / 255.0
        r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]
        mx = np.maximum(np.maximum(r, g), b)
        mn = np.minimum(np.minimum(r, g), b)
        sat = (mx - mn) / np.maximum(mx, 1e-6)        # per-pixel HSV saturation, 0..1
        boost = 1.0 + amount * (1.0 - sat)            # low-saturation pixels receive a larger multiplier
        gray = mx[:, :, np.newaxis]                    # use max channel as neutral reference
        out = arr + (arr - gray) * (boost[:, :, np.newaxis] - 1.0)
        return Image.fromarray((np.clip(out, 0, 1) * 255).astype(np.uint8))

    @staticmethod
    def _apply_sharpness(img: Image.Image, amount: float) -> Image.Image:
        """Unsharp mask sharpening (amount 0..1 maps to 0–200% strength).
        radius=1.2 and threshold=2 are tuned to avoid haloing on GIF frames."""
        if amount == 0:
            return img
        return img.filter(ImageFilter.UnsharpMask(
            radius=1.2, percent=int(amount * 200), threshold=2))

    @staticmethod
    def _apply_temperature(img: Image.Image, amount: float) -> Image.Image:
        """Warm (+) / cool (-) color temperature shift (amount -1..+1).
        Shifts red channel up and blue channel down for warmth (opposite for cool).
        Max delta of ±30 keeps the effect subtle enough for typical art use."""
        if amount == 0:
            return img
        r, g, b = img.split()
        def _shift(ch, delta):
            # int16 avoids uint8 wrap-around before clamp
            arr = np.array(ch, dtype=np.int16) + delta
            return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
        delta = int(amount * 30)  # ±30 pixel value shift at full strength
        return Image.merge("RGB", (_shift(r, delta), g, _shift(b, -delta)))

    def enhance_colors(self, image_path: Path, contrast: float = 1.5,
                       saturation: float = 1.3, vibrance: float = 0.0,
                       sharpness: float = 0.0, temperature: float = 0.0) -> Path:
        """Apply contrast, saturation, vibrance, sharpness, and temperature adjustments.
        Handles both static images and multi-frame GIFs. Returns path to the enhanced output file,
        or the original path if enhancement fails."""
        _enh_dir = self._workspace_dir(image_path, "mejorado")
        _enh_name = f"{image_path.stem}_enhanced{image_path.suffix}"
        self._archive_before_overwrite(_enh_dir, keep_names=[_enh_name])
        output_path = _enh_dir / _enh_name
        
        logger.info(f"🎨 Mejorando colores: contraste={contrast}, saturación={saturation}")
        
        try:
            # CORRECCIÓN 1: Verificar archivo de entrada
            if not image_path.exists():
                raise Exception(f"Archivo de entrada no existe: {image_path}")
            
            file_size = image_path.stat().st_size
            if file_size < 1024:
                raise Exception(f"Archivo de entrada muy pequeño: {file_size} bytes")
            
            # CORRECCIÓN 2: Verificar que es un archivo válido
            try:
                with Image.open(image_path) as test_img:
                    # PIL reports format as 'JPEG' for .jpg files, 'WEBP' for .webp, etc.
                    _SUPPORTED = {'GIF', 'PNG', 'JPEG', 'WEBP', 'BMP'}
                    if test_img.format not in _SUPPORTED:
                        raise Exception(f"Formato no soportado: {test_img.format}")
            except Exception as validation_error:
                raise Exception(f"Archivo corrupto o formato no soportado: {validation_error}")
            
            with Image.open(image_path) as img:
                if img.format == 'GIF':
                    frames = []
                    durations = []
                    
                    logger.info(f"🎞️ Procesando {getattr(img, 'n_frames', 1)} frames...")
                    
                    # CORRECCIÓN 3: Manejo robusto de frames
                    frame_count = 0
                    max_frames = 500  # cap to avoid OOM on very long GIFs
                    
                    try:
                        for frame_idx, frame in enumerate(ImageSequence.Iterator(img)):
                            if frame_count >= max_frames:
                                logger.warning(f"⚠️ Limitando a {max_frames} frames para estabilidad")
                                break
                                
                            try:
                                # Crear copia del frame para evitar problemas de referencia
                                frame_copy = frame.copy()
                                
                                # Convertir a RGB si es necesario
                                if frame_copy.mode != 'RGB':
                                    if frame_copy.mode == 'P':
                                        # Palette mode: go through RGBA to honour any transparent index before flattening
                                        frame_copy = frame_copy.convert('RGBA').convert('RGB')
                                    else:
                                        frame_copy = frame_copy.convert('RGB')
                                
                                # CORRECCIÓN 4: Aplicar mejoras con validación
                                try:
                                    # Contraste
                                    if 0.5 <= contrast <= 3.0:
                                        enhancer = ImageEnhance.Contrast(frame_copy)
                                        frame_copy = enhancer.enhance(contrast)

                                    # Saturación
                                    if 0.5 <= saturation <= 3.0:
                                        enhancer = ImageEnhance.Color(frame_copy)
                                        frame_copy = enhancer.enhance(saturation)

                                    # Vibrance (selective saturation)
                                    if vibrance > 0.01:
                                        frame_copy = self._apply_vibrance(frame_copy, vibrance)

                                    # Sharpness
                                    if sharpness > 0.01:
                                        frame_copy = self._apply_sharpness(frame_copy, sharpness)

                                    # Temperature
                                    if abs(temperature) > 0.01:
                                        frame_copy = self._apply_temperature(frame_copy, temperature)
                                    
                                except Exception as enhance_error:
                                    logger.error(f"⚠️ Error en frame {frame_count}: {enhance_error}")
                                    # Usar frame original si falla la mejora
                                    frame_copy = frame.convert('RGB')
                                
                                frames.append(frame_copy)
                                
                                # Duración del frame
                                duration = img.info.get('duration', 100)
                                # Some PIL versions expose duration as a list per-frame; others as a scalar
                                if isinstance(duration, (list, tuple)):
                                    if frame_idx < len(duration):
                                        durations.append(duration[frame_idx])
                                    else:
                                        durations.append(100)
                                else:
                                    durations.append(duration)
                                
                                frame_count += 1
                                
                            except Exception as frame_error:
                                logger.error(f"⚠️ Saltando frame {frame_idx}: {frame_error}")
                                continue
                        
                        if not frames:
                            raise Exception("No se procesaron frames válidos")
                        
                        logger.info(f"✅ Procesados {len(frames)} frames correctamente")
                        
                        # CORRECCIÓN 5: Guardar con configuración robusta
                        try:
                            # Usar duración promedio si hay inconsistencias
                            if durations:
                                avg_duration = sum(durations) / len(durations)
                                avg_duration = max(50, min(500, int(avg_duration)))  # clamp to safe GIF range
                            else:
                                avg_duration = 100
                            
                            frames[0].save(
                                output_path,
                                save_all=True,
                                append_images=frames[1:] if len(frames) > 1 else [],
                                duration=avg_duration,
                                loop=0,
                                optimize=False,  # skip PIL LZW optimiser; it can corrupt large GIFs
                                disposal=2,      # disposal=2: clear to background between frames
                            )
                            
                        except Exception as save_error:
                            logger.error(f"Error guardando GIF mejorado: {save_error}")
                            # Intentar guardar con configuración mínima
                            frames[0].save(
                                output_path,
                                save_all=True,
                                append_images=frames[1:] if len(frames) > 1 else [],
                                duration=100,
                                loop=0
                            )
                        
                    except Exception as processing_error:
                        raise Exception(f"Error procesando frames: {processing_error}")
                    
                else:
                    # CORRECCIÓN 6: Imagen estática
                    img_rgb = img.convert('RGB')

                    # Apply enhancements only when within safe multiplier ranges to avoid clipping
                    if 0.5 <= contrast <= 3.0:
                        img_rgb = ImageEnhance.Contrast(img_rgb).enhance(contrast)
                    if 0.5 <= saturation <= 3.0:
                        img_rgb = ImageEnhance.Color(img_rgb).enhance(saturation)
                    if vibrance > 0.01:
                        img_rgb = self._apply_vibrance(img_rgb, vibrance)
                    if sharpness > 0.01:
                        img_rgb = self._apply_sharpness(img_rgb, sharpness)
                    if abs(temperature) > 0.01:
                        img_rgb = self._apply_temperature(img_rgb, temperature)
                    img_rgb.save(output_path, quality=95, optimize=False)
            
            # CORRECCIÓN 7: Verificar resultado
            if not output_path.exists():
                raise Exception("Archivo mejorado no se creó")
            
            result_size = output_path.stat().st_size
            if result_size < 1024:
                output_path.unlink()  # Eliminar archivo corrupto
                raise Exception(f"Archivo mejorado corrupto: {result_size} bytes")
            
            size_mb = result_size / (1024 * 1024)
            logger.info(f"✅ Colores mejorados: {size_mb:.2f} MB")
            self._write_manifest(_enh_dir, "mejorar_colores",
                {"contrast": contrast, "saturation": saturation,
                 "vibrance": vibrance, "sharpness": sharpness, "temperature": temperature},
                archivos=[output_path], fuente=image_path)
            # Paso intermedio: no parchear trailer (rompería Pillow en siguientes pasos).
            return output_path

        except Exception as e:
            logger.error(f"❌ Error mejorando colores: {e}")
            
            # CORRECCIÓN 8: Limpiar archivo de salida corrupto
            if output_path.exists():
                try:
                    output_path.unlink()
                except Exception:
                    pass
            
            # Devolver archivo original si falla
            logger.info(f"↩️ Devolviendo archivo original: {image_path.name}")
            return image_path
        


    def interpolate_frames_to_60fps(self, gif_path: Path) -> Optional[Path]:
        """Duplicate frames to simulate 60 FPS playback from a lower-fps GIF.
        Note: this is frame repetition, not true optical-flow interpolation; it
        reduces perceived jitter without adding new visual information."""
        output_path = self._workspace_dir(gif_path, "interpolado") / f"{gif_path.stem}_60fps.gif"
        
        logger.info(f"⚡ Interpolando a 60 FPS: {gif_path}")
        
        try:
            with Image.open(gif_path) as img:
                original_frames = list(ImageSequence.Iterator(img))
                duration = img.info.get('duration', 100)
                current_fps = 1000 / duration if duration > 0 else 10
                
                logger.info(f"📊 FPS actual: {current_fps:.1f}")
                
                if current_fps >= 60:
                    logger.info("✅ El GIF ya tiene 60 FPS o más")
                    return gif_path
                
                interpolated_frames = []

                # Simple frame duplication: interleave each consecutive pair
                for i in tqdm(range(len(original_frames) - 1), desc="Interpolando"):
                    frame1 = original_frames[i].convert('RGBA')
                    frame2 = original_frames[i + 1].convert('RGBA')
                    interpolated_frames.append(frame1.convert('RGBA'))
                    interpolated_frames.append(frame2.convert('RGBA'))

                interpolated_frames = interpolated_frames[:-1]  # remove trailing duplicate of last frame

                frames = []
                for i in range(len(interpolated_frames)):
                    frames.append(interpolated_frames[i].convert('RGB'))

                # Frame count is doubled, so per-frame duration must be halved to keep
                # the total playback time unchanged (otherwise the GIF plays 2x slower).
                new_duration = max(20, int(1000 / (current_fps * 2)))
                frames[0].save(
                    output_path,
                    save_all=True,
                    append_images=frames[1:],
                    duration=new_duration,
                    loop=0,
                    optimize=False
                )

                # Paso intermedio: no parchear trailer.
                return output_path
        except Exception as e:
            logger.error(f"Error interpolando frames: {e}")
            return None

    def create_motion_blur_effect(self, gif_path: Path) -> Optional[Path]:
        """Apply a light motion blur for smoother animation."""
        import cv2
        import numpy as np

        output_path = self._workspace_dir(gif_path, "interpolado") / f"{gif_path.stem}_smooth.gif"

        try:
            with Image.open(gif_path) as img:
                # .copy() detaches each frame from the file; without it the lazy
                # frames reference a closed file once the with-block exits.
                frames = [f.copy() for f in ImageSequence.Iterator(img)]
                duration = img.info.get('duration', 100)

            blurred_frames = []
            for frame in frames:
                rgb = frame.convert('RGB')
                arr = np.array(rgb)
                # Horizontal motion-blur kernel: a 1×5 mean filter centred on row 2
                kernel = np.zeros((5, 5))
                kernel[2, :] = np.ones(5) / 5
                blurred = cv2.filter2D(arr, -1, kernel)
                # Blend 70% original + 30% blurred to keep the effect subtle
                result = cv2.addWeighted(arr, 0.7, blurred, 0.3, 0)
                blurred_frames.append(Image.fromarray(result))

            blurred_frames[0].save(
                output_path,
                save_all=True,
                append_images=blurred_frames[1:],
                duration=duration,
                loop=0,
                optimize=False,
            )
            # Paso intermedio: no parchear trailer.
            return output_path
        except Exception as e:
            logger.error(f"Error applying motion blur: {e}")
            return None



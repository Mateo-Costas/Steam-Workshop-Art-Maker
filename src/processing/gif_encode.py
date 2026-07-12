"""processing.gif_encode - GIF assembly, gifsicle/trailer post-processing, video->GIF."""
import os
import shutil
import platform
import subprocess
from pathlib import Path
from typing import Optional, List

from PIL import Image, ImageSequence

from processing.common import _NO_WINDOW_FLAGS, logger


class GifEncodeMixin:
    def create_optimized_gif(self, frame_paths: List[Path], output_path: Path, fps: int) -> bool:
        """Assemble a GIF from a list of frame paths at the configured Steam profile resolution.
        Tries up to three PIL save configurations, then falls back to FFmpeg. Returns True on success."""
        try:
            # CORRECCIÓN 1: Validación exhaustiva de entrada
            logger.info(f"🔍 create_optimized_gif iniciado:")
            logger.info(f"  - frame_paths: {len(frame_paths) if frame_paths else 0} frames")
            logger.info(f"  - output_path: {output_path}")
            logger.info(f"  - fps: {fps}")
            logger.info(f"  - CWD: {Path.cwd()}")
            
            if not frame_paths:
                logger.error("❌ Error: Lista de frames vacía")
                return False
            
            # CORRECCIÓN 2: Verificar que los frames existen
            valid_frames = []
            for i, frame_path in enumerate(frame_paths):
                if not isinstance(frame_path, Path):
                    logger.error(f"❌ Frame {i} no es Path válido: {type(frame_path)}")
                    continue
                
                if not frame_path.exists():
                    logger.error(f"❌ Frame {i} no existe: {frame_path}")
                    continue
                
                try:
                    # Verificar que se puede abrir
                    with Image.open(frame_path) as test_img:
                        if test_img.size[0] < 10 or test_img.size[1] < 10:
                            logger.error(f"❌ Frame {i} muy pequeño: {test_img.size}")
                            continue
                    valid_frames.append(frame_path)
                except Exception as e:
                    logger.error(f"❌ Frame {i} corrupto: {e}")
                    continue
            
            if not valid_frames:
                logger.error("❌ Error: No hay frames válidos")
                return False
            
            logger.info(f"✅ Frames válidos: {len(valid_frames)}/{len(frame_paths)}")
            
            target_size = (self.config.get('steam_profile.width'), self.config.get('steam_profile.height'))
            duration = max(50, min(500, int(1000 / fps)))  # clamp to 50–500 ms; avoids <50 ms flicker
            max_frames = min(len(valid_frames), 500)  # cap to avoid OOM on very long GIFs
            
            logger.info(f"📊 Configuración:")
            logger.info(f"  - Target size: {target_size}")
            logger.info(f"  - Duration: {duration}ms")
            logger.info(f"  - Max frames: {max_frames}")
            
            # CORRECCIÓN 4: Procesar frames con manejo de memoria
            frames = []
            processed_count = 0
            
            try:
                for i in range(max_frames):
                    frame_path = valid_frames[i]
                    
                    try:
                        # Cargar frame
                        with Image.open(frame_path) as img:
                            # Convertir a RGB
                            if img.mode != 'RGB':
                                if img.mode == 'RGBA':
                                    # Composite RGBA over white; GIF has no real alpha channel
                                    rgb_img = Image.new('RGB', img.size, (255, 255, 255))
                                    rgb_img.paste(img, mask=img.split()[-1])  # split()[-1] is the alpha channel
                                    frame = rgb_img
                                else:
                                    frame = img.convert('RGB')
                            else:
                                frame = img.copy()
                            
                            # Redimensionar si es necesario
                            if frame.size != target_size:
                                frame = frame.resize(target_size, Image.Resampling.LANCZOS)
                            
                            # Agregar a lista
                            frames.append(frame)
                            processed_count += 1
                            
                            # Log progreso cada 50 frames
                            if processed_count % 50 == 0:
                                logger.info(f"  📊 Procesados: {processed_count}/{max_frames} frames")
                    
                    except Exception as frame_error:
                        logger.error(f"⚠️ Error en frame {i}: {frame_error}")
                        continue
                    
                    if processed_count % 100 == 0:
                        import gc
                        gc.collect()  # periodic collection prevents unbounded RAM growth on large GIFs
                
                if not frames:
                    logger.error("❌ Error: No se cargaron frames")
                    return False
                
                logger.info(f"✅ Frames cargados: {len(frames)}")
                
            except Exception as loading_error:
                logger.error(f"❌ Error cargando frames: {loading_error}")
                return False
            
            # CORRECCIÓN 6: Asegurar directorio de salida
            try:
                output_path.parent.mkdir(parents=True, exist_ok=True)
                logger.info(f"✅ Directorio de salida verificado: {output_path.parent}")
            except Exception as dir_error:
                logger.error(f"❌ Error creando directorio: {dir_error}")
                return False
            
            save_attempts = [
                # Attempt 1: disposal=2 (clear to background) — cleanest for animated GIFs
                {
                    "optimize": False,  # skip PIL LZW optimiser; it can corrupt large GIFs
                    "disposal": 2,
                    "transparency": None,
                    "background": None
                },
                # Attempt 2: disposal=0 (do not dispose) — some encoders need this
                {
                    "optimize": False,
                    "disposal": 0,
                },
                # Attempt 3: bare minimum — let PIL use its defaults
                {}
            ]
            
            for attempt, save_params in enumerate(save_attempts, 1):
                try:
                    logger.info(f"💾 Intento {attempt} de guardado...")
                    
                    # Crear archivo temporal
                    temp_path = output_path.with_suffix('.tmp.gif')
                    
                    # Guardar GIF
                    frames[0].save(
                        temp_path,
                        save_all=True,
                        append_images=frames[1:] if len(frames) > 1 else [],
                        duration=duration,
                        loop=0,
                        **save_params
                    )
                    
                    # Verificar que se creó correctamente
                    if temp_path.exists():
                        file_size = temp_path.stat().st_size
                        
                        if file_size > 1024:  # Al menos 1KB
                            # Verificar que es un GIF válido
                            try:
                                with Image.open(temp_path) as test_gif:
                                    if test_gif.format == 'GIF':
                                        # ¡Éxito! Mover a ubicación final
                                        if output_path.exists():
                                            output_path.unlink()
                                        
                                        import shutil
                                        shutil.move(temp_path, output_path)

                                        # NO parchear aquí: el AI 4x es intermedio,
                                        # el split/enhance posterior necesita Pillow.
                                        final_size = output_path.stat().st_size / (1024 * 1024)
                                        logger.info(f"✅ GIF creado exitosamente: {final_size:.2f} MB")
                                        
                                        # Liberar memoria
                                        for frame in frames:
                                            try:
                                                frame.close()
                                            except Exception:
                                                pass
                                        
                                        import gc
                                        gc.collect()

                                        self._try_gifsicle_optimize(output_path)
                                        return True
                                    else:
                                        logger.error(f"❌ Intento {attempt}: Archivo no es GIF válido")
                            except Exception as validation_error:
                                logger.error(f"❌ Intento {attempt}: Validación falló: {validation_error}")
                        else:
                            logger.error(f"❌ Intento {attempt}: Archivo muy pequeño ({file_size} bytes)")
                        
                        # Limpiar archivo temporal fallido
                        if temp_path.exists():
                            temp_path.unlink()
                    else:
                        logger.error(f"❌ Intento {attempt}: Archivo temporal no se creó")
                    
                except Exception as save_error:
                    logger.error(f"❌ Intento {attempt} falló: {save_error}")
                    
                    # Limpiar archivo temporal si existe
                    temp_path = output_path.with_suffix('.tmp.gif')
                    if temp_path.exists():
                        try:
                            temp_path.unlink()
                        except Exception:
                            pass
                    
                    continue
            
            # CORRECCIÓN 8: Fallback con FFmpeg
            logger.info("🔄 Todos los intentos PIL fallaron, probando FFmpeg...")
            
            if self.check_ffmpeg():
                try:
                    return self._create_gif_with_ffmpeg(valid_frames, output_path, fps)
                except Exception as ffmpeg_error:
                    logger.error(f"❌ FFmpeg también falló: {ffmpeg_error}")
            else:
                logger.error("❌ FFmpeg no disponible")
            
            # CORRECCIÓN 9: Limpieza final
            logger.error("❌ Error: No se pudo crear GIF con ningún método")
            
            # Liberar memoria
            try:
                for frame in frames:
                    try:
                        frame.close()
                    except Exception:
                        pass
            except Exception:
                pass
            
            import gc
            gc.collect()
            
            return False
            
        except Exception as critical_error:
            logger.error(f"❌ Error crítico en create_optimized_gif: {critical_error}")
            import traceback
            traceback.print_exc()
            return False

    def _create_gif_with_ffmpeg(self, frame_paths: List[Path], output_path: Path, fps: int) -> bool:
        """Fallback GIF encoder using FFmpeg's 2-pass palette pipeline (palettegen + paletteuse)."""
        try:
            if not self.check_ffmpeg():
                logger.error("❌ FFmpeg no disponible")
                return False
            
            # Usar el patrón de nombres de los frames
            if frame_paths:
                first_frame = frame_paths[0]
                # Detectar el patrón del nombre
                frame_pattern = first_frame.parent / "frame_%06d.png"
                
                width = self.config.get('steam_profile.width')
                height = self.config.get('steam_profile.height')
                
                cmd = [
                    str(self.ffmpeg_path),
                    "-framerate", str(fps),
                    "-i", str(frame_pattern),
                    "-vf", (
                        f"scale={width}:{height}:flags=lanczos,"         # resize with high-quality Lanczos
                        f"split[s0][s1];"                                  # duplicate stream for 2-pass palette
                        f"[s0]palettegen=max_colors=256:stats_mode=full[p];"  # pass 1: build full-clip palette
                        f"[s1][p]paletteuse=dither=sierra2_4a"            # pass 2: apply sierra2_4a dither (best for gradients)
                    ),
                    "-y", str(output_path)
                ]
                
                logger.info(f"🔧 Comando FFmpeg: {' '.join(cmd)}")
                
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=300, **_NO_WINDOW_FLAGS)
                
                if result.returncode == 0 and output_path.exists():
                    size_mb = output_path.stat().st_size / (1024 * 1024)
                    logger.info(f"✅ GIF creado con FFmpeg: {size_mb:.2f} MB")
                    self._patch_gif_trailer(output_path)
                    self._try_gifsicle_optimize(output_path)
                    return True
                else:
                    logger.error(f"❌ FFmpeg error: {result.stderr}")
                    return False
            else:
                logger.error("❌ No hay frames para procesar")
                return False
            
        except Exception as e:
            logger.error(f"❌ Error con FFmpeg: {e}")
            return False
    
    def _optimize_gif_size(self, gif_path: Path, max_size_mb: float):
        """Reduce GIF palette depth to bring file size below max_size_mb, then run gifsicle for LZW recompression."""
        current_size_mb = gif_path.stat().st_size / (1024 * 1024)
        
        if current_size_mb <= max_size_mb:
            return
        
        try:
            logger.info(f"🔧 Optimizando GIF de {current_size_mb:.2f} MB a {max_size_mb:.2f} MB...")
            
            # Reducir colores para reducir tamaño
            with Image.open(gif_path) as img:
                frames = list(ImageSequence.Iterator(img))
                duration = img.info.get('duration', 100)
                
                # Scale color count proportionally to target size ratio; clamp to [32, 256]
                reduction_factor = max_size_mb / current_size_mb
                new_colors = int(256 * reduction_factor)
                new_colors = max(32, min(256, new_colors))
                
                logger.info(f"🎨 Reduciendo a {new_colors} colores...")
                
                # Re-quantize each frame with an adaptive palette of new_colors entries
                optimized_frames = []
                for frame in frames:
                    frame = frame.convert('RGB').convert('P', palette=Image.ADAPTIVE, colors=new_colors)
                    optimized_frames.append(frame)
                
                # Guardar versión optimizada
                temp_path = gif_path.with_suffix('.tmp.gif')
                optimized_frames[0].save(
                    temp_path,
                    save_all=True,
                    append_images=optimized_frames[1:],
                    duration=duration,
                    loop=0,
                    optimize=False
                )
                
                # Reemplazar si es más pequeño
                if temp_path.stat().st_size < gif_path.stat().st_size:
                    shutil.move(temp_path, gif_path)
                    new_size = gif_path.stat().st_size / (1024 * 1024)
                    logger.info(f"✅ GIF optimizado (colores): {new_size:.2f} MB")
                else:
                    temp_path.unlink()
                    logger.warning("⚠️ La optimización no redujo el tamaño")

            # Segundo pase con gifsicle (lossless LZW recompression)
            self._try_gifsicle_optimize(gif_path)
                    
        except Exception as e:
            logger.error(f"❌ Error optimizando tamaño: {e}")
    
    def _download_gifsicle(self) -> Optional[Path]:
        """Auto-descarga gifsicle.exe para Windows si no está instalado."""
        if platform.system() != "Windows":
            found = shutil.which("gifsicle")
            return Path(found) if found else None

        dest = self.base_path / "SteamWorkshopAppData" / "gifsicle.exe"
        if dest.exists():
            self.gifsicle_path = dest
            return dest

        url = "https://github.com/kohler/gifsicle/releases/download/v1.94/gifsicle-1.94-win64.zip"
        fallback_url = "https://eternallybored.org/misc/gifsicle/releases/gifsicle-1.94-win64.zip"
        import zipfile, tempfile
        for try_url in (url, fallback_url):
            try:
                import requests as _req
                resp = _req.get(try_url, stream=True, timeout=30)
                resp.raise_for_status()
                # mkstemp instead of the race-prone deprecated mktemp
                _fd, _tmp_name = tempfile.mkstemp(suffix=".zip")
                tmp = Path(_tmp_name)
                with os.fdopen(_fd, "wb") as f:
                    for chunk in resp.iter_content(8192):
                        if chunk:
                            f.write(chunk)
                with zipfile.ZipFile(tmp) as zf:
                    for name in zf.namelist():
                        if name.lower().endswith("gifsicle.exe"):
                            dest.parent.mkdir(parents=True, exist_ok=True)
                            with zf.open(name) as src, open(dest, "wb") as tgt:
                                tgt.write(src.read())
                            break
                tmp.unlink(missing_ok=True)
                if dest.exists():
                    logger.info(f"gifsicle descargado: {dest}")
                    self.gifsicle_path = dest
                    return dest
            except Exception as e:
                logger.warning(f"gifsicle descarga fallida ({try_url}): {e}")
        return None

    def _try_gifsicle_optimize(self, gif_path: Path, lossy: int = 0) -> None:
        """Run gifsicle --optimize=3 for lossless LZW recompression in-place.
        lossy > 0 enables lossy compression (--lossy flag) for larger size reductions.
        Only replaces the file if gifsicle produces a smaller result."""
        exe = self.gifsicle_path
        if not exe or not exe.exists():
            exe = self._download_gifsicle()
        if not exe:
            return

        out = gif_path.with_stem(gif_path.stem + "_gs")  # temporary output path
        cmd = [str(exe), "--optimize=3", "-o", str(out), str(gif_path)]
        if lossy > 0:
            cmd.insert(1, f"--lossy={lossy}")  # lossy must come before --optimize
        try:
            result = subprocess.run(cmd, capture_output=True, timeout=120, **_NO_WINDOW_FLAGS)
            if result.returncode == 0 and out.exists():
                orig_size = gif_path.stat().st_size
                new_size = out.stat().st_size
                if new_size < orig_size:
                    gif_path.unlink()
                    out.rename(gif_path)
                    saved_kb = (orig_size - new_size) / 1024
                    logger.info(f"gifsicle: {orig_size/1048576:.2f} → {new_size/1048576:.2f} MB (−{saved_kb:.0f} KB)")
                else:
                    out.unlink()
            elif out.exists():
                out.unlink()
        except Exception as e:
            logger.warning(f"gifsicle optimization failed: {e}")
            if out.exists():
                out.unlink()


    def _patch_gif_trailer(self, path: Path) -> bool:
        """Replace trailing 0x3B with 0x21 so Steam renders full-size in showcase.
        Returns True if patched, False if not needed or file invalid."""
        if not self.patch_trailer_for_steam:
            return False
        try:
            if not path or not path.exists():
                return False
            if path.stat().st_size < 1:
                return False
            with open(path, "r+b") as f:
                f.seek(-1, os.SEEK_END)
                last_byte = f.read(1)
                if last_byte == b'\x3B':
                    # 0x3B is the standard GIF89a trailer; Steam truncates display when it finds it.
                    # Replacing with 0x21 (Extension Introducer) prevents premature termination.
                    f.seek(-1, os.SEEK_END)
                    f.write(b'\x21')
                    logger.info(f"🩹 Trailer GIF parcheado para Steam: {path.name}")
                    return True
                if last_byte == b'\x21':
                    return False  # already patched
                return False
        except (IOError, OSError) as e:
            logger.warning(f"No se pudo parchear trailer de {path}: {e}")
            return False

    def _modify_gif_hex(self, file_path: Path):
        self._patch_gif_trailer(file_path)
    
    def convert_video_to_gif(self, video_path: Path, output_path: Path, fps: int = 24) -> Optional[Path]:
        """Convert any FFmpeg-readable video to a GIF at the configured Steam profile resolution.
        Uses 2-pass palette (palettegen + paletteuse) for optimal color quality. Returns output path or None."""
        if not self.check_ffmpeg():
            logger.error("❌ FFmpeg no disponible para conversión de video")
            return None
        
        width = self.config.get('steam_profile.width')
        height = self.config.get('steam_profile.height')
        
        logger.info(f"🎬 Convirtiendo video a GIF: {video_path} -> {output_path}")
        logger.info(f"📊 Configuración: {width}x{height} @ {fps} FPS")
        
        cmd = [
            str(self.ffmpeg_path),
            "-i", str(video_path),
            "-vf", (
                f"fps={fps},"                                              # resample to target frame rate
                f"scale={width}:{height}:flags=lanczos,"                  # resize with Lanczos
                f"split[s0][s1];"                                          # duplicate for 2-pass palette
                f"[s0]palettegen=max_colors=256:stats_mode=full[p];"      # pass 1: global palette
                f"[s1][p]paletteuse=dither=sierra2_4a"                    # pass 2: apply dither
            ),
            "-y", str(output_path)
        ]
        
        try:
            result = subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=120, **_NO_WINDOW_FLAGS)
            size_mb = output_path.stat().st_size / (1024 * 1024)
            logger.info(f"✅ Video convertido: {size_mb:.2f} MB")
            # NO parcheamos el trailer aquí: es un paso intermedio y Pillow
            # no puede leer GIFs con 0x21 al final. El parche se aplica solo
            # en fragmentos finales (split) y en el uploader.
            return output_path
        except subprocess.TimeoutExpired:
            logger.error("❌ Timeout convirtiendo video (>2 minutos)")
            return None
        except Exception as e:
            logger.error(f"❌ Error convirtiendo video: {e}")
            return None


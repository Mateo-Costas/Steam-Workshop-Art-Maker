"""
processor.py - Procesador principal de imagenes/video para WorkshopArt PRO
"""
import sys
import os
import shutil
import platform
import subprocess
import logging
from pathlib import Path
from typing import Optional, List, Tuple, Callable
from PIL import Image, ImageSequence, ImageEnhance
from tqdm import tqdm
from config import Config
from models import ModelManager
from analyzers import ContentAnalyzer

# Hide subprocess console windows on Windows
_NO_WINDOW_FLAGS = {'creationflags': subprocess.CREATE_NO_WINDOW} if platform.system() == 'Windows' else {}


logger = logging.getLogger("WorkshopArtPRO.processor")

class SteamProcessor:
    """Procesador principal de imágenes, video y GIFs para Steam Workshop."""
    
    def __init__(self, config: Config):
        self.config = config
        self.model_manager = ModelManager(Path(config.get('paths.models')))
        self.content_analyzer = ContentAnalyzer()
        self.use_gpu = config.get('gpu.use_gpu', True)
        self.gpu_id = config.get('gpu.gpu_id', 0)
        
        if getattr(sys, 'frozen', False):
            # Ejecutando desde PyInstaller
            self.base_path = Path(sys.executable).parent
        else:
            # Ejecutando como script Python
            self.base_path = Path.cwd()
        
        logger.info(f"🔍 Base path detectado: {self.base_path}")
        
        # Rutas de ejecutables
        self.ffmpeg_path = self._find_executable("ffmpeg")
        self.realesrgan_path = self._find_executable("realesrgan-ncnn-vulkan")
        self.realcugan_path = self._find_executable("realcugan-ncnn-vulkan")
        self.rife_path = self._find_executable("rife-ncnn-vulkan")

        logger.info(f"FFmpeg: {self.ffmpeg_path}")
        logger.info(f"Real-ESRGAN: {self.realesrgan_path}")
        logger.info(f"Real-CUGAN: {self.realcugan_path}")
        logger.info(f"RIFE: {self.rife_path}")

        # Cache for GPU detection (avoid repeated wmic/subprocess calls)
        self._gpu_cache: Optional[Tuple[bool, str]] = None

        self.patch_trailer_for_steam = True

    # Workspace: <stem>_workshop/<categoria>/ junto al archivo fuente.
    _WORKSPACE_SUFFIX_TOKEN = "_workshop"
    _WORKSPACE_SUFFIXES = (
        "_AI_4x", "_enhanced", "_60fps", "_smooth", "_opt", "_optimized",
        "_converted", "_resized_temp", "_artwork_resized_temp",
    )

    def _strip_workspace_suffix(self, stem: str) -> str:
        import re
        stem = re.sub(r"_RIFE\d+x_\d+$", "", stem)
        stem = re.sub(r"_part_\d+$", "", stem)
        stem = re.sub(r"_artwork_(main|side)$", "", stem)
        for s in self._WORKSPACE_SUFFIXES:
            if stem.endswith(s):
                stem = stem[: -len(s)]
                break
        return stem

    def _workspace_root(self, source: Path) -> Path:
        """Devuelve la carpeta <stem>_workshop/ real, remontando si la fuente
        ya vive dentro de un workshop existente."""
        token = self._WORKSPACE_SUFFIX_TOKEN
        # Remontar si source está dentro de un *_workshop/
        for parent in source.parents:
            if parent.name.endswith(token):
                return parent
        root_stem = self._strip_workspace_suffix(source.stem)
        return source.parent / f"{root_stem}{token}"

    def _workspace_dir(self, source: Path, category: str) -> Path:
        out = self._workspace_root(source) / category
        out.mkdir(parents=True, exist_ok=True)
        return out

    def get_fragments_dir(self, source: Path) -> Path:
        """Devuelve la ruta donde se guardan los fragmentos creados a partir
        de `source`. Útil para que la UI localice los archivos reales."""
        return self._workspace_root(source) / "fragmentos"

    def list_fragments(self, source: Path, pattern: str = "_part_") -> List[Path]:
        """Lista fragmentos en la carpeta workspace (GIF, JPEG o PNG).
        `pattern` filtra por subcadena del nombre (ej. '_part_' o 'artwork_')."""
        frag_dir = self.get_fragments_dir(source)
        if not frag_dir.exists():
            return []
        return sorted(p for p in frag_dir.iterdir()
                      if p.is_file()
                      and p.suffix.lower() in {".gif", ".jpg", ".jpeg", ".png"}
                      and pattern in p.name)

    def _archive_before_overwrite(self, out_dir: Path, keep_names: Optional[List[str]] = None) -> None:
        """Limpia la carpeta de salida antes de una nueva corrida.
        Borra archivos sueltos (excepto los listados en keep_names y manifest.json)
        y cualquier subcarpeta residual como _historico. Sin archivado."""
        if not out_dir.exists():
            return
        keep = set(keep_names or [])
        for p in out_dir.iterdir():
            try:
                if p.is_file():
                    if p.name in keep or p.name == "manifest.json":
                        continue
                    p.unlink()
                elif p.is_dir():
                    shutil.rmtree(p, ignore_errors=True)
            except Exception as e:
                logger.warning(f"No se pudo limpiar {p.name}: {e}")

    def _write_manifest(self, out_dir: Path, operacion: str, parametros: dict,
                        archivos: Optional[List[Path]] = None,
                        fuente: Optional[Path] = None) -> None:
        """Escribe manifest.json con traza de la corrida."""
        import json as _json
        import time as _t
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
            data = {
                "operacion": operacion,
                "fecha": _t.strftime("%Y-%m-%d %H:%M:%S"),
                "fuente": str(fuente) if fuente else None,
                "parametros": parametros,
                "archivos": [
                    {"nombre": p.name,
                     "tamano_mb": round(p.stat().st_size / (1024 * 1024), 3)}
                    for p in (archivos or []) if p and p.exists()
                ],
            }
            (out_dir / "manifest.json").write_text(
                _json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        except Exception as e:
            logger.warning(f"No se pudo escribir manifest: {e}")

    def _find_executable(self, name: str) -> Optional[Path]:
        # Extensión según sistema
        ext = ".exe" if platform.system() == "Windows" else ""
        filename = f"{name}{ext}"
        
        # Lugares donde buscar
        search_paths = [
            self.base_path / filename,  # Junto al exe
            self.base_path / "_internal" / filename,  # Dentro de _internal
            Path.cwd() / filename,  # Directorio actual
        ]
        
        # Buscar en cada ubicación
        for path in search_paths:
            if path.exists():
                logger.info(f"✅ Encontrado {name} en: {path}")
                return path
        
        # Buscar en PATH del sistema
        system_path = shutil.which(name)
        if system_path:
            logger.info(f"✅ Encontrado {name} en PATH: {system_path}")
            return Path(system_path)
        
        logger.error(f"❌ No se encontró {name}")
        return None

    def check_gpu_available(self, force: bool = False) -> Tuple[bool, str]:
        """Verificar disponibilidad de GPU MEJORADA (cacheada)"""
        if self._gpu_cache is not None and not force:
            return self._gpu_cache
        result = self._check_gpu_uncached()
        self._gpu_cache = result
        return result

    def _check_gpu_uncached(self) -> Tuple[bool, str]:
        try:
            # Método 1: Verificar directamente con el ejecutable de Real-ESRGAN
            if self.realesrgan_path and self.realesrgan_path.exists():
                try:
                    # Ejecutar con --help para verificar GPU
                    result = subprocess.run(
                        [str(self.realesrgan_path), "-h"], 
                        capture_output=True, text=True, timeout=10, **_NO_WINDOW_FLAGS
                    )
                    
                    if result.returncode == 0 or "Usage:" in (result.stdout + result.stderr):
                        # El ejecutable funciona, ahora verificar GPU
                        try:
                            # Intentar listar GPUs
                            gpu_result = subprocess.run(
                                [str(self.realesrgan_path), "-g", "-1", "-h"], 
                                capture_output=True, text=True, timeout=5, **_NO_WINDOW_FLAGS
                            )
                            
                            output = gpu_result.stderr + gpu_result.stdout
                            if "AMD" in output:
                                return True, "AMD GPU detectada (Real-ESRGAN compatible)"
                            elif "NVIDIA" in output:
                                return True, "NVIDIA GPU detectada (Real-ESRGAN compatible)"
                            elif "vulkan" in output.lower():
                                return True, "GPU Vulkan compatible detectada"
                            else:
                                return True, "GPU detectada por Real-ESRGAN"
                        except Exception:
                            # Si no podemos verificar GPU específica, asumir que funciona
                            return True, "GPU compatible (Real-ESRGAN disponible)"
                except Exception as e:
                    logger.error(f"Error verificando con Real-ESRGAN: {e}")
            
            # Método 2: Verificar con wmic (Windows)
            if platform.system() == "Windows":
                try:
                    result = subprocess.run(
                        ['wmic', 'path', 'win32_VideoController', 'get', 'name'], 
                        capture_output=True, text=True, timeout=10, **_NO_WINDOW_FLAGS
                    )
                    if result.returncode == 0:
                        gpu_info = result.stdout.lower()
                        
                        # Buscar AMD
                        if 'amd' in gpu_info or 'radeon' in gpu_info:
                            lines = result.stdout.strip().split('\n')
                            for line in lines:
                                if 'amd' in line.lower() or 'radeon' in line.lower():
                                    clean_line = line.strip()
                                    if clean_line and clean_line != "Name":
                                        return True, f"AMD: {clean_line}"
                            return True, "AMD GPU detectada"
                        
                        # Buscar NVIDIA
                        elif 'nvidia' in gpu_info or 'geforce' in gpu_info:
                            lines = result.stdout.strip().split('\n')
                            for line in lines:
                                if 'nvidia' in line.lower() or 'geforce' in line.lower():
                                    clean_line = line.strip()
                                    if clean_line and clean_line != "Name":
                                        return True, f"NVIDIA: {clean_line}"
                            return True, "NVIDIA GPU detectada"
                        
                        # Buscar Intel
                        elif 'intel' in gpu_info:
                            return True, "Intel GPU detectada (soporte limitado)"
                except Exception as e:
                    logger.error(f"Error con wmic: {e}")
            
            return False, "No se detectó GPU compatible"
            
        except Exception as e:
            logger.error(f"Error general detectando GPU: {e}")
            return False, f"Error detectando GPU: {e}"
        
    def check_ffmpeg(self) -> bool:
        """Verificar disponibilidad de ffmpeg"""
        return self.ffmpeg_path is not None and self.ffmpeg_path.exists()
    
    def extract_gif_frames(self, gif_path: Path, output_dir: Path) -> Tuple[Optional[List[Path]], Optional[int]]:
        """Extraer frames de un GIF"""
        try:
            output_dir.mkdir(exist_ok=True)
            
            with Image.open(gif_path) as gif:
                frames = []
                durations = []
                
                for i, frame in enumerate(ImageSequence.Iterator(gif)):
                    frame_rgb = frame.copy().convert("RGB")
                    frame_path = output_dir / f"frame_{i:06d}.png"
                    frame_rgb.save(frame_path, "PNG")
                    frames.append(frame_path)
                    
                    duration = gif.info.get('duration', 100)
                    durations.append(duration)
                
                avg_duration = sum(durations) / len(durations) if durations else 100
                return frames, int(avg_duration)
        except Exception as e:
            logger.error(f"Error extrayendo frames: {e}")
            return None, None
    
    def extract_video_frames(self, video_path: Path, output_dir: Path) -> Optional[float]:
        """Extraer frames de un video"""
        try:
            output_dir.mkdir(exist_ok=True)
            from moviepy.editor import VideoFileClip

            with VideoFileClip(str(video_path)) as clip:
                fps = clip.fps
                total_frames = int(clip.fps * clip.duration)
                
                for i, frame in enumerate(tqdm(clip.iter_frames(), total=total_frames, desc="Extrayendo frames")):
                    frame_path = output_dir / f"frame_{i:06d}.png"
                    Image.fromarray(frame).save(frame_path, "PNG")
                
                return fps
        except Exception as e:
            logger.error(f"Error extrayendo frames del video: {e}")
            return None
    
    def upscale_frames_batch(self, input_dir: Path, output_dir: Path,
                           model_name: str = "realesrgan-x4plus",
                           use_gpu: bool = True,
                           progress_callback: Optional[Callable] = None) -> Optional[List[Path]]:
        """Upscale frames con Real-ESRGAN o Real-CUGAN"""
        output_dir.mkdir(exist_ok=True)

        # Verificar que hay frames de entrada
        input_frames = list(input_dir.glob("*.png"))
        if not input_frames:
            if progress_callback:
                progress_callback("Error: No hay frames de entrada", 0)
            return None

        # Limpiar nombre del modelo (puede venir con descripcion)
        clean_model_name = model_name.split(" - ")[0].split(" ")[0]

        # Detectar si es un modelo CUGAN
        model_info = self.model_manager.get_model_info(clean_model_name)
        engine = model_info.get("engine", "realesrgan")

        gpu_id = "0" if use_gpu else "-1"

        if engine == "realcugan":
            # --- Real-CUGAN ---
            exe_path = self.realcugan_path
            if not exe_path or not exe_path.exists():
                if progress_callback:
                    progress_callback("Error: Real-CUGAN no encontrado", 0)
                return None

            cugan_args = model_info.get("cugan_args", {})
            scale = str(cugan_args.get("scale", 2))
            noise = str(cugan_args.get("noise", 0))
            model_dir = cugan_args.get("model_dir", "models-se")

            # Ruta al directorio de modelos relativa al exe
            models_path = exe_path.parent / model_dir

            cmd = [
                str(exe_path),
                "-i", str(input_dir),
                "-o", str(output_dir),
                "-s", scale,
                "-n", noise,
                "-m", str(models_path),
                "-f", "png",
                "-g", gpu_id,
            ]
            working_dir = exe_path.parent
            logger.info(f"CUGAN: scale={scale} noise={noise} models={model_dir}")
        else:
            # --- Real-ESRGAN ---
            exe_path = self.realesrgan_path
            if not exe_path or not exe_path.exists():
                if progress_callback:
                    progress_callback("Error: Real-ESRGAN no encontrado", 0)
                return None

            cmd = [
                str(exe_path),
                "-i", str(input_dir),
                "-o", str(output_dir),
                "-n", clean_model_name,
                "-s", "4",
                "-f", "png",
                "-g", gpu_id,
            ]
            working_dir = exe_path.parent
        try:
            if progress_callback:
                mode = "GPU" if use_gpu else "CPU"
                progress_callback(f"🚀 Iniciando procesamiento con {mode}...", 20)
            
            logger.info(f"🔧 Ejecutando: {' '.join(cmd)}")
            logger.info(f"📂 Entrada: {input_dir} ({len(input_frames)} frames)")
            logger.info(f"📁 Salida: {output_dir}")
            logger.info(f"🎯 Modelo: {clean_model_name}")
            logger.info(f"⚡ Modo: {'GPU' if use_gpu else 'CPU'}")
            
            # Ejecutar con manejo de salida mejorado
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=str(working_dir),**_NO_WINDOW_FLAGS
            )

            # Watcher: cuenta PNGs producidos en output_dir y reporta progreso
            # en vivo, así el usuario ve avance en vez de quedarse mirando 0.
            import threading as _th, time as _time
            total_in = len(input_frames)
            stop_watch = _th.Event()
            start_ts = _time.time()

            def _watch():
                last_done = -1
                while not stop_watch.is_set():
                    try:
                        done = sum(1 for _ in output_dir.glob("*.png"))
                    except Exception:
                        done = last_done
                    if done != last_done:
                        last_done = done
                        elapsed = _time.time() - start_ts
                        rate = done / elapsed if elapsed > 0 else 0
                        eta = ((total_in - done) / rate) if rate > 0.01 else 0
                        pct_inner = int((done / total_in) * 100) if total_in else 0
                        # Mapear a rango 20-80 del progreso global
                        pct = 20 + int((done / total_in) * 60) if total_in else 20
                        msg = (f"🤖 IA: {done}/{total_in} frames "
                               f"({pct_inner}%, {rate:.2f} f/s, ETA {int(eta)}s)")
                        if progress_callback:
                            try:
                                progress_callback(msg, pct)
                            except Exception:
                                pass
                    stop_watch.wait(2.0)

            watcher = _th.Thread(target=_watch, daemon=True)
            watcher.start()

            # Timeout escalado con el número de frames: base 5 min + 5 s/frame,
            # mínimo 10 min. Para 1300 frames ≈ 2 h.
            dyn_timeout = max(600, 300 + 5 * total_in)
            try:
                stdout, stderr = process.communicate(timeout=dyn_timeout)
                return_code = process.returncode
            except subprocess.TimeoutExpired:
                process.kill()
                stop_watch.set()
                if progress_callback:
                    progress_callback(
                        f"❌ Timeout tras {dyn_timeout}s en IA", 0)
                logger.error(f"❌ Timeout: IA tardó más de {dyn_timeout}s")
                return None
            finally:
                stop_watch.set()
            
            logger.info(f"📊 Código de salida: {return_code}")
            if stdout:
                logger.info(f"📄 Salida: {stdout[:200]}...")
            if stderr:
                logger.error(f"⚠️ Errores: {stderr[:400]}...")
            
            if return_code == 0:
                # Verificar archivos de salida
                upscaled_frames = sorted(list(output_dir.glob("*.png")))
                
                if upscaled_frames:
                    if progress_callback:
                        progress_callback(f"✅ Procesamiento completado: {len(upscaled_frames)} frames", 80)
                    logger.info(f"✅ Éxito: {len(upscaled_frames)} frames procesados")
                    return upscaled_frames
                else:
                    if progress_callback:
                        progress_callback("❌ Error: No se generaron frames de salida", 0)
                    logger.error("❌ Error: No se generaron archivos de salida")
                    return None
            else:
                # CORRECCIÓN CRÍTICA 3: Mejor manejo de errores GPU
                if use_gpu and "invalid gpu device" in stderr:
                    if progress_callback:
                        progress_callback("⚠️ GPU no válida, reintentando con CPU...", 60)
                    logger.warning("⚠️ GPU no válida, reintentando con CPU...")
                    return self.upscale_frames_batch(
                        input_dir, output_dir, clean_model_name,  # Usar nombre limpio
                        use_gpu=False, progress_callback=progress_callback
                    )
                elif use_gpu and return_code != 0:
                    if progress_callback:
                        progress_callback("⚠️ Error con GPU, reintentando con CPU...", 60)
                    logger.error("⚠️ Error con GPU, reintentando con CPU...")
                    return self.upscale_frames_batch(
                        input_dir, output_dir, clean_model_name,  # Usar nombre limpio
                        use_gpu=False, progress_callback=progress_callback
                    )
                else:
                    if progress_callback:
                        progress_callback(f"❌ Error en procesamiento (código {return_code})", 0)
                    logger.error(f"❌ Error: código {return_code}")
                    logger.info(f"stderr: {stderr}")
                    
                    # DIAGNÓSTICO ADICIONAL
                    if "failed" in stderr and "param" in stderr:
                        logger.error("Diagnostico: Error de modelo")
                        logger.info(f"   Modelo buscado: {clean_model_name}")
                        models_dir = self.model_manager.models_dir
                        available = [f.stem for f in models_dir.glob("*.bin")]
                        logger.info(f"   Modelos disponibles: {available}")
                        
                        # Intentar con primer modelo disponible
                        if available:
                            alternative = available[0]
                            logger.info(f"   🔄 Reintentando con modelo: {alternative}")
                            return self.upscale_frames_batch(
                                input_dir, output_dir, alternative,
                                use_gpu=use_gpu, progress_callback=progress_callback
                            )
                    
                    return None
                
        except Exception as e:
            if progress_callback:
                progress_callback(f"❌ Error: {e}", 0)
            logger.error(f"❌ Excepción: {e}")
            return None
        
        
    
    
    def create_optimized_gif(self, frame_paths: List[Path], output_path: Path, fps: int) -> bool:
        """Crear GIF optimizado - VERSIÓN COMPLETAMENTE CORREGIDA"""
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
            
            # CORRECCIÓN 3: Configurar parámetros seguros
            target_size = (self.config.get('steam_profile.width'), self.config.get('steam_profile.height'))
            duration = max(50, min(500, int(1000 / fps)))  # Entre 50ms y 500ms
            max_frames = min(len(valid_frames), 500)  # Máximo 500 frames para estabilidad
            
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
                                    # Crear fondo blanco para transparencias
                                    rgb_img = Image.new('RGB', img.size, (255, 255, 255))
                                    rgb_img.paste(img, mask=img.split()[-1])
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
                    
                    # CORRECCIÓN 5: Liberar memoria cada 100 frames
                    if processed_count % 100 == 0:
                        import gc
                        gc.collect()
                
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
            
            # CORRECCIÓN 7: Crear GIF con múltiples intentos
            save_attempts = [
                # Intento 1: Configuración óptima
                {
                    "optimize": False,
                    "disposal": 2,
                    "transparency": None,
                    "background": None
                },
                # Intento 2: Configuración básica
                {
                    "optimize": False,
                    "disposal": 0,
                },
                # Intento 3: Configuración mínima
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
        """Crear GIF usando FFmpeg como alternativa"""
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
                    "-vf", f"scale={width}:{height}:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=256:stats_mode=diff[p];[s1][p]paletteuse=dither=bayer:bayer_scale=5",
                    "-y", str(output_path)
                ]
                
                logger.info(f"🔧 Comando FFmpeg: {' '.join(cmd)}")
                
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=300, **_NO_WINDOW_FLAGS)
                
                if result.returncode == 0 and output_path.exists():
                    size_mb = output_path.stat().st_size / (1024 * 1024)
                    logger.info(f"✅ GIF creado con FFmpeg: {size_mb:.2f} MB")
                    self._patch_gif_trailer(output_path)
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
        """Optimizar tamaño del GIF si excede el límite"""
        current_size_mb = gif_path.stat().st_size / (1024 * 1024)
        
        if current_size_mb <= max_size_mb:
            return
        
        try:
            logger.info(f"🔧 Optimizando GIF de {current_size_mb:.2f} MB a {max_size_mb:.2f} MB...")
            
            # Reducir colores para reducir tamaño
            with Image.open(gif_path) as img:
                frames = list(ImageSequence.Iterator(img))
                duration = img.info.get('duration', 100)
                
                # Calcular reducción necesaria
                reduction_factor = max_size_mb / current_size_mb
                new_colors = int(256 * reduction_factor)
                new_colors = max(32, min(256, new_colors))
                
                logger.info(f"🎨 Reduciendo a {new_colors} colores...")
                
                # Recrear GIF con menos colores
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
                    logger.info(f"✅ GIF optimizado: {new_size:.2f} MB")
                else:
                    temp_path.unlink()
                    logger.warning("⚠️ La optimización no redujo el tamaño")
                    
        except Exception as e:
            logger.error(f"❌ Error optimizando tamaño: {e}")
    
    def split_gif_for_steam(self, gif_path: Path) -> bool:
        """Fragmentar GIF en 5 partes para Steam - VERSIÓN CORREGIDA"""
        if not self.check_ffmpeg():
            logger.error("❌ FFmpeg no disponible - necesario para fragmentación")
            return False
        output_dir = self._workspace_dir(gif_path, "fragmentos")
        self._archive_before_overwrite(output_dir)
        output_prefix = output_dir / gif_path.stem
        _source_for_manifest = gif_path
        logger.info(f"✂️ Fragmentando: {gif_path}")
        logger.info(f"📁 Salida en: {output_dir}")

        original_gif_path = gif_path
        try:
            logger.info(f"✂️ Fragmentando GIF: {gif_path}")

            # Verificar y ajustar dimensiones primero
            with Image.open(gif_path) as img:
                expected_width = self.config.get('steam_profile.width')
                expected_height = self.config.get('steam_profile.height')
                
                logger.info(f"📐 Dimensiones actuales: {img.size}, esperadas: {expected_width}x{expected_height}")
                
                if img.size != (expected_width, expected_height):
                    logger.info(f"🔧 Redimensionando de {img.size} a {expected_width}x{expected_height}")
                    
                    # Crear GIF redimensionado
                    frames = []
                    durations = []
                    
                    for frame in ImageSequence.Iterator(img):
                        resized = frame.resize((expected_width, expected_height), Image.Resampling.LANCZOS)
                        frames.append(resized)
                        durations.append(img.info.get('duration', 100))
                    
                    # Guardar GIF temporal redimensionado
                    temp_resized = gif_path.with_stem(f"{gif_path.stem}_resized_temp")
                    frames[0].save(
                        temp_resized,
                        save_all=True,
                        append_images=frames[1:],
                        duration=durations[0] if durations else 100,
                        loop=0,
                        optimize=False
                    )
                    gif_path = temp_resized
                    logger.info(f"✅ GIF redimensionado guardado: {gif_path}")
            
            output_prefix = gif_path.with_suffix('')
            section_width = expected_width // 5
            height = expected_height
            
            logger.info(f"📊 Fragmentando en secciones de {section_width}x{height} px")
            
            # Fragmentar usando ffmpeg con configuración mejorada
            success = True
            created_parts = []
            
            for i in range(5):
                left = i * section_width
                output_path = output_dir / f"{gif_path.stem}_part_{i+1}.gif"
                
                logger.info(f"✂️ Creando parte {i+1}/5: {output_path.name}")
                
                # Comando ffmpeg mejorado para evitar artefactos
                cmd = [
                    str(self.ffmpeg_path),
                    "-i", str(gif_path),
                    "-vf", f"crop={section_width}:{height}:{left}:0,split[s0][s1];[s0]palettegen=max_colors=256:reserve_transparent=1:stats_mode=diff[p];[s1][p]paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle",
                    "-y",
                    str(output_path)
                ]
                
                try:
                    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60, **_NO_WINDOW_FLAGS)
                    if result.returncode == 0:
                        self._patch_gif_trailer(output_path)

                        # Verificar tamaño
                        if not output_path.exists():
                            logger.error(f"❌ Parte {i+1}: FFmpeg no creó el archivo")
                            success = False
                            break
                        size_mb = output_path.stat().st_size / (1024 * 1024)
                        created_parts.append({
                            "part": i+1,
                            "path": output_path,
                            "size": size_mb
                        })
                        logger.info(f"✅ Parte {i+1} creada: {size_mb:.2f} MB")
                    else:
                        logger.error(f"❌ Error en parte {i+1}: {result.stderr}")
                        success = False
                        break
                except subprocess.TimeoutExpired:
                    logger.error(f"❌ Timeout en parte {i+1}")
                    success = False
                    break
                except Exception as e:
                    logger.error(f"❌ Excepción en parte {i+1}: {e}")
                    success = False
                    break
            
            # Limpiar archivo temporal si se creó
            if gif_path != original_gif_path and gif_path.exists():
                gif_path.unlink()
                logger.info("🧹 Archivo temporal eliminado")
            
            if success and len(created_parts) == 5:
                self._write_manifest(output_dir, "fragmentar_steam",
                    {"partes": 5, "section_width": section_width, "height": height},
                    archivos=[p['path'] for p in created_parts],
                    fuente=_source_for_manifest)
                logger.info(f"\n✅ Fragmentación completada exitosamente!")
                logger.info("📊 Resumen de partes creadas:")
                
                total_size = 0
                min_size = self.config.get('steam_profile.min_size_mb', 4.4)
                max_size = self.config.get('steam_profile.max_size_mb', 4.8)
                
                for part in created_parts:
                    size = part['size']
                    total_size += size
                    status = "✅" if min_size <= size <= max_size else "⚠️"
                    logger.info(f"  {status} {part['path'].name}: {size:.2f} MB")
                
                logger.info(f"📊 Tamaño total: {total_size:.2f} MB")
                
                # Verificar advertencias
                warnings = []
                for part in created_parts:
                    if part['size'] < min_size:
                        warnings.append(f"Parte {part['part']} muy pequeña ({part['size']:.2f} MB)")
                    elif part['size'] > max_size:
                        warnings.append(f"Parte {part['part']} muy grande ({part['size']:.2f} MB)")
                
                if warnings:
                    logger.warning("\n⚠️ Advertencias:")
                    for warning in warnings:
                        logger.warning(f"  • {warning}")
                    logger.info("Steam Workshop puede tener problemas con estos archivos.")
                
                return True
            else:
                logger.error(f"❌ Fragmentación falló: solo {len(created_parts)}/5 partes creadas")
                return False
            
        except Exception as e:
            logger.error(f"❌ Error en fragmentación: {e}")
            return False

    def split_gif_for_artwork_showcase(self, gif_path: Path, output_dir=None) -> bool:
        """Fragmentar GIF en 2 partes (main 506 + side 100) para Steam Artwork Showcase.

        Specs (Steam 2026): formatos aceptados jpg/gif/png, max 5 MiB por pieza.
        Regular showcase = main 506px ancho + side 100px ancho (alto LIBRE, cualquier valor).
        Featured showcase = 630px ancho único.

        Calidad — pipeline optimizado:
          - Sin pre-resize con PIL (evita doble cuantización).
          - Un solo ffmpeg por parte con scale lanczos + 2-pass palette en filter_complex.
          - palettegen stats_mode=full (palette óptima sobre TODO el clip).
          - paletteuse dither=sierra2_4a (mejor dither para gradientes/animación).
          - Reintento adaptativo: si > 4.9 MiB, baja max_colors (256→192→128→96) y
            luego fps si hace falta. Mantiene calidad máxima dentro del límite.
          - Altura preservada: si el fuente no es 606 ancho, reescala por lanczos
            manteniendo aspecto (no fuerza 506 alto — showcase acepta cualquier alto).
        """
        if not self.check_ffmpeg():
            logger.error("❌ FFmpeg no disponible - necesario para fragmentación")
            return False

        if output_dir is None:
            output_dir = self._workspace_dir(gif_path, "fragmentos")
        output_dir = Path(output_dir)
        self._archive_before_overwrite(output_dir)
        _artwork_src = gif_path

        main_width = self.config.get('artwork_showcase.main_width', 506)
        side_width = self.config.get('artwork_showcase.side_width', 100)
        total_width = main_width + side_width  # 606
        # Alto: showcase acepta cualquier alto. Preservar el del fuente (escalado
        # proporcionalmente a 606 ancho). Config puede forzar un alto fijo.
        forced_height = self.config.get('artwork_showcase.height', 0)  # 0 = auto
        MAX_BYTES = 5 * 1024 * 1024 - 16 * 1024  # 5 MiB menos margen
        STEAM_HARD_MAX = 5 * 1024 * 1024

        logger.info(f"🎨 Fragmentando para Artwork Showcase: {gif_path}")

        try:
            # Leer dimensiones y fps reales
            with Image.open(gif_path) as img:
                orig_w, orig_h = img.size
                orig_duration = img.info.get('duration', 100) or 100
            orig_fps = 1000.0 / max(1, orig_duration)
            logger.info(f"📐 Origen: {orig_w}x{orig_h} @ ~{orig_fps:.2f}fps")

            # Calcular alto target preservando aspecto (o forzado por config)
            if forced_height and forced_height > 0:
                target_height = int(forced_height)
            else:
                target_height = max(1, round(orig_h * total_width / max(1, orig_w)))
            # ffmpeg prefiere alto par para algunos codecs; GIF no exige pero
            # mejor redondear a par para evitar artefactos en filtros.
            if target_height % 2 == 1:
                target_height += 1
            logger.info(f"📐 Target: {main_width}+{side_width}={total_width} × {target_height}")

            parts_config = [
                {"name": "artwork_main", "width": main_width, "left": 0},
                {"name": "artwork_side", "width": side_width, "left": main_width},
            ]

            # Grados de calidad — primero intenta el máximo, baja si no cabe
            # (colors, fps_cap). fps_cap=None = preservar fps original.
            quality_ladder = [
                (256, None),
                (256, 24),
                (192, 24),
                (160, 20),
                (128, 20),
                (96, 15),
                (64, 12),
            ]

            created_parts = []
            success = True

            for part in parts_config:
                out_path = output_dir / f"{gif_path.stem}_{part['name']}.gif"
                chosen = None
                last_err = ""
                for colors, fps_cap in quality_ladder:
                    # Construir cadena de filtros: scale lanczos → crop → 2-pass palette
                    fps_part = f"fps={fps_cap}," if fps_cap else ""
                    # scale al total_width manteniendo aspecto a target_height
                    scale = f"scale={total_width}:{target_height}:flags=lanczos+accurate_rnd+full_chroma_int"
                    crop = f"crop={part['width']}:{target_height}:{part['left']}:0"
                    # Palette en el MISMO clip recortado (por-zona → mejor fidelidad)
                    filter_complex = (
                        f"[0:v]{fps_part}{scale},{crop},split[a][b];"
                        f"[a]palettegen=max_colors={colors}:stats_mode=full:reserve_transparent=1[p];"
                        f"[b][p]paletteuse=dither=sierra2_4a:diff_mode=rectangle"
                    )
                    cmd = [
                        str(self.ffmpeg_path),
                        "-i", str(gif_path),
                        "-filter_complex", filter_complex,
                        "-loop", "0",
                        "-y",
                        str(out_path),
                    ]
                    logger.info(f"✂️ {part['name']}: colors={colors} fps={fps_cap or 'orig'} → {out_path.name}")
                    try:
                        result = subprocess.run(cmd, capture_output=True, text=True,
                                                timeout=180, **_NO_WINDOW_FLAGS)
                        if result.returncode != 0:
                            last_err = (result.stderr or "")[-400:]
                            logger.warning(f"   ffmpeg rc={result.returncode}: {last_err[-200:]}")
                            continue
                        if not out_path.exists():
                            last_err = "ffmpeg no creó el archivo"
                            continue
                        size = out_path.stat().st_size
                        logger.info(f"   → {size/1024/1024:.2f} MiB (límite {STEAM_HARD_MAX/1024/1024:.2f})")
                        if size <= MAX_BYTES:
                            chosen = (colors, fps_cap, size)
                            break
                        # Demasiado grande — probar siguiente tier
                    except subprocess.TimeoutExpired:
                        last_err = "timeout"
                        logger.warning(f"   timeout con colors={colors} fps={fps_cap}")
                        continue
                    except Exception as e:
                        last_err = str(e)
                        logger.warning(f"   excepción: {e}")
                        continue

                if chosen is None:
                    logger.error(f"❌ {part['name']}: no se pudo generar bajo {STEAM_HARD_MAX/1024/1024:.2f} MiB. último error: {last_err}")
                    success = False
                    break

                self._patch_gif_trailer(out_path)
                colors, fps_cap, size = chosen
                size_mb = size / (1024 * 1024)
                created_parts.append({
                    "name": part['name'],
                    "path": out_path,
                    "size": size_mb,
                    "colors": colors,
                    "fps_cap": fps_cap,
                })
                logger.info(f"✅ {part['name']}: {size_mb:.2f} MiB (colors={colors}, fps={fps_cap or 'orig'})")

            if success and len(created_parts) == 2:
                self._write_manifest(output_dir, "fragmentar_artwork_showcase",
                    {"main_width": main_width, "side_width": side_width,
                     "height": target_height,
                     "calidad": [{"parte": p['name'], "colors": p['colors'], "fps_cap": p['fps_cap']}
                                 for p in created_parts]},
                    archivos=[p['path'] for p in created_parts],
                    fuente=_artwork_src)
                logger.info(f"\n✅ Fragmentación Artwork Showcase completada!")
                total_size = sum(p['size'] for p in created_parts)
                for part in created_parts:
                    status = "✅" if part['size'] * 1024 * 1024 <= STEAM_HARD_MAX else "⚠️"
                    logger.info(f"  {status} {part['path'].name}: {part['size']:.2f} MiB")
                logger.info(f"📊 Total: {total_size:.2f} MiB")
                return True
            else:
                logger.error(f"❌ Fragmentación falló: {len(created_parts)}/2 partes creadas")
                return False

        except Exception as e:
            logger.error(f"❌ Error en fragmentación Artwork Showcase: {e}")
            return False

    def _split_image_into_jpeg_parts(self, image_path: Path,
                                      parts: list, total_w: int, fixed_h,
                                      output_dir: Path,
                                      manifest_op: str, manifest_params: dict) -> bool:
        """Crop a static image into JPEG panels using ffmpeg. Internal helper."""
        try:
            created = []
            for (name, w, left) in parts:
                out_path = output_dir / f"{image_path.stem}_{name}.jpg"
                if fixed_h:
                    vf = (f"scale={total_w}:{fixed_h}"
                          f":force_original_aspect_ratio=increase"
                          f":flags=lanczos+accurate_rnd+full_chroma_int,"
                          f"crop={total_w}:{fixed_h},"
                          f"crop={w}:{fixed_h}:{left}:0")
                else:
                    vf = (f"scale={total_w}:-2"
                          f":flags=lanczos+accurate_rnd+full_chroma_int,"
                          f"crop={w}:ih:{left}:0")
                cmd = [str(self.ffmpeg_path), "-i", str(image_path),
                       "-vf", vf, "-q:v", "2", "-y", str(out_path)]
                logger.info(f"✂️ {name}: {out_path.name}")
                r = subprocess.run(cmd, capture_output=True, text=True,
                                   timeout=60, **_NO_WINDOW_FLAGS)
                if r.returncode != 0 or not out_path.exists():
                    logger.error(f"❌ {name}: {(r.stderr or '')[-200:]}")
                    return False
                size_mb = out_path.stat().st_size / (1024 * 1024)
                logger.info(f"✅ {name}: {size_mb:.2f} MiB")
                created.append(out_path)
            self._write_manifest(output_dir, manifest_op, manifest_params,
                                 archivos=created, fuente=image_path)
            return True
        except Exception as e:
            logger.error(f"❌ _split_image_into_jpeg_parts: {e}")
            return False

    def split_image_for_artwork_showcase(self, image_path: Path, output_dir=None) -> bool:
        """Split static image (JPG/PNG) into JPEG panels (main 506px + side 100px)."""
        if not self.check_ffmpeg():
            logger.error("❌ FFmpeg no disponible")
            return False
        image_path = Path(image_path)
        if output_dir is None:
            output_dir = self._workspace_dir(image_path, "fragmentos")
        output_dir = Path(output_dir)
        self._archive_before_overwrite(output_dir)
        main_width = self.config.get('artwork_showcase.main_width', 506)
        side_width = self.config.get('artwork_showcase.side_width', 100)
        total_width = main_width + side_width
        forced_height = self.config.get('artwork_showcase.height', 0)
        fixed_h = int(forced_height) if forced_height and int(forced_height) > 0 else None
        parts = [("artwork_main", main_width, 0), ("artwork_side", side_width, main_width)]
        logger.info(f"🎨 Fragmentando imagen para Artwork Showcase: {image_path}")
        return self._split_image_into_jpeg_parts(
            image_path, parts, total_width, fixed_h, output_dir,
            "fragmentar_artwork_showcase_image",
            {"main_width": main_width, "side_width": side_width, "format": "jpeg"},
        )

    def split_image_for_showcase(self, image_path: Path, preset: str, output_dir=None) -> bool:
        """Split static image (JPG/PNG) into JPEG panels per showcase preset."""
        if preset not in self.SHOWCASE_PRESETS:
            logger.error(f"❌ Preset desconocido: {preset}")
            return False
        if not self.check_ffmpeg():
            logger.error("❌ FFmpeg no disponible")
            return False
        image_path = Path(image_path)
        cfg = self.SHOWCASE_PRESETS[preset]
        if output_dir is None:
            output_dir = self._workspace_dir(image_path, "fragmentos")
        output_dir = Path(output_dir)
        self._archive_before_overwrite(output_dir)
        logger.info(f"🎨 Preset '{preset}' (imagen) → {cfg['desc']}")
        return self._split_image_into_jpeg_parts(
            image_path, cfg["parts"], cfg["total_w"], cfg["fixed_h"], output_dir,
            f"fragmentar_showcase_image_{preset}",
            {"preset": preset, "format": "jpeg"},
        )

    # ---- Presets para showcases (layouts verificados en foros Steam 2025) ----
    # Cada preset define:
    #   parts: lista de (name, width_px, left_offset_px) para recortar el source
    #   total_w: ancho total al que escalar el source antes de recortar
    #   fixed_h: alto forzado (None = preservar aspecto del source)
    #   upload_hint: modo sugerido para subir ("artwork"/"screenshot"/"workshop")
    SHOWCASE_PRESETS = {
        # 1 slot — sin fragmentar
        "featured_630": {
            "parts": [("featured", 630, 0)], "total_w": 630, "fixed_h": None,
            "upload_hint": "artwork",
            "desc": "Featured Artwork 630×H (1 slot grande)",
        },
        "artwork_single_630": {
            "parts": [("single", 630, 0)], "total_w": 630, "fixed_h": 354,
            "upload_hint": "artwork",
            "desc": "Artwork single 630×354 (sin side image, 16:9)",
        },
        "screenshot_638": {
            "parts": [("screenshot", 638, 0)], "total_w": 638, "fixed_h": 354,
            "upload_hint": "screenshot",
            "desc": "Screenshot Showcase 638×354 (1 slot, file_type=5)",
        },
        # 2 slots — layout artwork normal
        "artwork_2part": {
            "parts": [("artwork_main", 506, 0), ("artwork_side", 100, 506)],
            "total_w": 606, "fixed_h": None,
            "upload_hint": "artwork",
            "desc": "Artwork 506+100 (main+side, alto libre)",
        },
        # 4 slots — grid artwork
        "artwork_4grid": {
            "parts": [(f"artwork_g{i+1}", 245, 245*i) for i in range(4)],
            "total_w": 980, "fixed_h": 245,
            "upload_hint": "artwork",
            "desc": "Artwork 4-grid 4×245 cuadrados",
        },
        # 4 slots — screenshot 4-grid
        "screenshot_4grid": {
            "parts": [(f"ss_g{i+1}", 638, 638*i) for i in range(4)],
            "total_w": 2552, "fixed_h": 354,
            "upload_hint": "screenshot",
            "desc": "Screenshot 4-grid 4×638×354 (file_type=5)",
        },
        # 5 slots workshop 150×150 (sin bordes)
        "workshop_5slot_150": {
            "parts": [(f"ws_s{i+1}", 150, 150*i) for i in range(5)],
            "total_w": 750, "fixed_h": 150,
            "upload_hint": "workshop",
            "desc": "Workshop Showcase 5×150×150",
        },
        # 5 slots workshop 119×119 (tamaño real del grid)
        "workshop_5slot_119": {
            "parts": [(f"ws_s{i+1}", 119, 119*i) for i in range(5)],
            "total_w": 595, "fixed_h": 119,
            "upload_hint": "workshop",
            "desc": "Workshop Showcase 5×119×119 (tamaño nativo)",
        },
        # 5 slots panorama artwork — banner horizontal 3150×360
        "panorama_5_630": {
            "parts": [(f"pano_{i+1}", 630, 630*i) for i in range(5)],
            "total_w": 3150, "fixed_h": 360,
            "upload_hint": "artwork",
            "desc": "Panorama artwork 5×630×360 (banner horizontal)",
        },
    }

    def split_gif_for_showcase(self, gif_path: Path, preset: str,
                               output_dir: Optional[Path] = None) -> bool:
        """Fragmenta un GIF según preset de showcase.

        Pipeline idéntico a split_gif_for_artwork_showcase (2-pass palette + ladder
        de calidad), pero parametrizado por preset. Garantiza trailer-patch y
        tamaño ≤ 5 MiB por parte.
        """
        if preset not in self.SHOWCASE_PRESETS:
            logger.error(f"❌ Preset desconocido: {preset}")
            return False
        if not self.check_ffmpeg():
            logger.error("❌ FFmpeg no disponible")
            return False

        cfg = self.SHOWCASE_PRESETS[preset]
        parts_cfg = cfg["parts"]
        total_w = cfg["total_w"]
        fixed_h = cfg["fixed_h"]

        if output_dir is None:
            output_dir = self._workspace_dir(gif_path, "fragmentos")
        output_dir = Path(output_dir)
        self._archive_before_overwrite(output_dir)

        MAX_BYTES = 5 * 1024 * 1024 - 16 * 1024
        STEAM_HARD_MAX = 5 * 1024 * 1024

        logger.info(f"🎨 Preset '{preset}' → {cfg['desc']}")
        try:
            with Image.open(gif_path) as img:
                orig_w, orig_h = img.size

            if fixed_h:
                target_h = int(fixed_h)
            else:
                target_h = max(1, round(orig_h * total_w / max(1, orig_w)))
            if target_h % 2 == 1:
                target_h += 1
            logger.info(f"📐 Target: {total_w}×{target_h}, {len(parts_cfg)} parte(s)")

            quality_ladder = [
                (256, None), (256, 24), (192, 24), (160, 20),
                (128, 20), (96, 15), (64, 12),
            ]

            created = []
            for (name, w, left) in parts_cfg:
                out_path = output_dir / f"{gif_path.stem}_{name}.gif"
                chosen = None
                last_err = ""
                for colors, fps_cap in quality_ladder:
                    fps_part = f"fps={fps_cap}," if fps_cap else ""
                    if fixed_h:
                        # Preset con alto fijo: escalar preservando ratio hasta cubrir
                        # total_w×fixed_h y recortar centro (sin distorsión ni barras).
                        scale = (
                            f"scale={total_w}:{target_h}"
                            f":force_original_aspect_ratio=increase"
                            f":flags=lanczos+accurate_rnd+full_chroma_int,"
                            f"crop={total_w}:{target_h}"
                        )
                        crop = f"crop={w}:{target_h}:{left}:0"
                    else:
                        # Alto libre: escalar al ancho exacto preservando ratio.
                        # Usar ih en crop para evitar desfase de 1px entre Python y FFmpeg.
                        scale = (
                            f"scale={total_w}:-2"
                            f":flags=lanczos+accurate_rnd+full_chroma_int"
                        )
                        crop = f"crop={w}:ih:{left}:0"
                    filter_complex = (
                        f"[0:v]{fps_part}{scale},{crop},split[a][b];"
                        f"[a]palettegen=max_colors={colors}:stats_mode=full:reserve_transparent=1[p];"
                        f"[b][p]paletteuse=dither=sierra2_4a:diff_mode=rectangle"
                    )
                    cmd = [str(self.ffmpeg_path), "-i", str(gif_path),
                           "-filter_complex", filter_complex, "-loop", "0",
                           "-y", str(out_path)]
                    try:
                        r = subprocess.run(cmd, capture_output=True, text=True,
                                           timeout=180, **_NO_WINDOW_FLAGS)
                        if r.returncode != 0:
                            last_err = (r.stderr or "")[-200:]
                            continue
                        if not out_path.exists():
                            last_err = "ffmpeg no creó el archivo"
                            continue
                        sz = out_path.stat().st_size
                        if sz <= MAX_BYTES:
                            chosen = (colors, fps_cap, sz)
                            break
                    except subprocess.TimeoutExpired:
                        last_err = "timeout"
                        continue
                    except Exception as e:
                        last_err = str(e)
                        continue
                if chosen is None:
                    logger.error(f"❌ {name}: no generado ≤ {STEAM_HARD_MAX/1024/1024:.1f} MiB. {last_err}")
                    return False
                self._patch_gif_trailer(out_path)
                c, fc, sz = chosen
                created.append({"name": name, "path": out_path,
                                "size": sz/1024/1024, "colors": c, "fps_cap": fc})
                logger.info(f"✅ {name}: {sz/1024/1024:.2f} MiB (c={c}, fps={fc or 'orig'})")

            self._write_manifest(output_dir, f"showcase_{preset}",
                {"preset": preset, "total_w": total_w, "height": target_h,
                 "parts": [{"n": p["name"], "colors": p["colors"], "fps": p["fps_cap"]}
                           for p in created]},
                archivos=[p["path"] for p in created], fuente=gif_path)
            logger.info(f"✅ Preset '{preset}' completado: {len(created)} parte(s)")
            return True
        except Exception as e:
            logger.error(f"❌ Error preset '{preset}': {e}")
            return False

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
                    f.seek(-1, os.SEEK_END)
                    f.write(b'\x21')
                    logger.info(f"🩹 Trailer GIF parcheado para Steam: {path.name}")
                    return True
                if last_byte == b'\x21':
                    return False
                return False
        except (IOError, OSError) as e:
            logger.warning(f"No se pudo parchear trailer de {path}: {e}")
            return False

    def _modify_gif_hex(self, file_path: Path):
        self._patch_gif_trailer(file_path)
    
    def convert_video_to_gif(self, video_path: Path, output_path: Path, fps: int = 24) -> Optional[Path]:
        """Convertir video a GIF"""
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
            "-vf", f"fps={fps},scale={width}:{height}:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=256:stats_mode=diff[p];[s1][p]paletteuse=dither=bayer:bayer_scale=5",
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
    
    def enhance_colors(self, image_path: Path, contrast: float = 1.5, saturation: float = 1.3) -> Path:
        """Mejorar colores y contraste - VERSIÓN CORREGIDA"""
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
                    if test_img.format not in ['GIF', 'PNG', 'JPEG', 'JPG']:
                        raise Exception(f"Formato no soportado: {test_img.format}")
            except Exception as validation_error:
                raise Exception(f"Archivo corrupto: {validation_error}")
            
            with Image.open(image_path) as img:
                if img.format == 'GIF':
                    frames = []
                    durations = []
                    
                    logger.info(f"🎞️ Procesando {getattr(img, 'n_frames', 1)} frames...")
                    
                    # CORRECCIÓN 3: Manejo robusto de frames
                    frame_count = 0
                    max_frames = 500  # Limitar frames para evitar memoria excesiva
                    
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
                                        # Paleta - convertir preservando transparencias
                                        frame_copy = frame_copy.convert('RGBA').convert('RGB')
                                    else:
                                        frame_copy = frame_copy.convert('RGB')
                                
                                # CORRECCIÓN 4: Aplicar mejoras con validación
                                try:
                                    # Contraste
                                    if 0.5 <= contrast <= 3.0:  # Rango seguro
                                        enhancer = ImageEnhance.Contrast(frame_copy)
                                        frame_copy = enhancer.enhance(contrast)
                                    
                                    # Saturación
                                    if 0.5 <= saturation <= 3.0:  # Rango seguro
                                        enhancer = ImageEnhance.Color(frame_copy)
                                        frame_copy = enhancer.enhance(saturation)
                                    
                                except Exception as enhance_error:
                                    logger.error(f"⚠️ Error en frame {frame_count}: {enhance_error}")
                                    # Usar frame original si falla la mejora
                                    frame_copy = frame.convert('RGB')
                                
                                frames.append(frame_copy)
                                
                                # Duración del frame
                                duration = img.info.get('duration', 100)
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
                                avg_duration = max(50, min(500, int(avg_duration)))  # Rango seguro
                            else:
                                avg_duration = 100
                            
                            frames[0].save(
                                output_path,
                                save_all=True,
                                append_images=frames[1:] if len(frames) > 1 else [],
                                duration=avg_duration,
                                loop=0,
                                optimize=False,  # No optimizar para mantener calidad
                                disposal=2,      # Limpiar frame anterior
                                transparency=0   # Evitar problemas de transparencia
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
                    
                    # Aplicar mejoras
                    if 0.5 <= contrast <= 3.0:
                        enhancer = ImageEnhance.Contrast(img_rgb)
                        img_rgb = enhancer.enhance(contrast)
                    
                    if 0.5 <= saturation <= 3.0:
                        enhancer = ImageEnhance.Color(img_rgb)
                        img_rgb = enhancer.enhance(saturation)
                    
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
                {"contrast": contrast, "saturation": saturation},
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
        """Interpolar frames para simular 60 FPS"""
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
                
                frame_multiplier = int(60 / current_fps)
                logger.info(f"🔢 Multiplicador de frames: {frame_multiplier}")
                
                interpolated_frames = []
                
                for i in tqdm(range(len(original_frames) - 1), desc="Interpolando"):
                    frame1 = original_frames[i].convert('RGBA')
                    frame2 = original_frames[i + 1].convert('RGBA')
                    interpolated_frames.append(frame1.convert('RGBA'))
                    interpolated_frames.append(frame2.convert('RGBA'))
                
                interpolated_frames = interpolated_frames[:-1]
                
                frames = []
                for i in range(len(interpolated_frames)):
                    frames.append(interpolated_frames[i].convert('RGB'))
                
                frames[0].save(
                    output_path,
                    save_all=True,
                    append_images=frames[1:],
                    duration=int(1000 / current_fps),
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
                frames = list(ImageSequence.Iterator(img))
                duration = img.info.get('duration', 100)

            blurred_frames = []
            for frame in frames:
                rgb = frame.convert('RGB')
                arr = np.array(rgb)
                kernel = np.zeros((5, 5))
                kernel[2, :] = np.ones(5) / 5
                blurred = cv2.filter2D(arr, -1, kernel)
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

    def shrink_to_size_cap(self, gif_path: Path,
                           max_mb: float = 5.0,
                           min_mb: float = 4.7,
                           progress_cb: Optional[Callable[[str], None]] = None) -> Optional[Path]:
        """Reducir un GIF por debajo de max_mb manteniendo máxima calidad.

        Busca el resultado con mayor tamaño que quepa en [min_mb, max_mb].
        Si no logra bajar de max_mb, devuelve el mejor candidato por debajo
        y loguea advertencia. No modifica el archivo original; escribe
        <stem>_opt.gif al lado.
        """
        def log(msg: str):
            logger.info(msg)
            if progress_cb:
                try:
                    progress_cb(msg)
                except Exception:
                    pass

        if not self.ffmpeg_path:
            log("FFmpeg no disponible")
            return None
        if not gif_path.exists():
            log(f"No existe: {gif_path}")
            return None

        original_mb = gif_path.stat().st_size / (1024 * 1024)
        log(f"Tamaño original: {original_mb:.2f} MB (objetivo ≤ {max_mb:.2f} MB)")

        if original_mb <= max_mb and original_mb >= min_mb:
            log("Ya cumple el rango, no hay que tocarlo")
            return gif_path

        # Parámetros ordenados de mayor a menor calidad.
        # (fps_divisor, max_colors, scale_factor) — cada tupla es una estrategia.
        # IMPORTANTE: scale SIEMPRE 1.0 → no redimensionamos nunca, porque si
        # un fragmento queda con dimensiones distintas al resto, el long-artwork
        # sale descompensado en el perfil. Solo bajamos fps y paleta de colores.
        # Sweep gradual de 45 fases: primero bajamos colores manteniendo fps
        # original, luego combinamos reducción de fps + colores progresivamente.
        strategies: List[Tuple[str, int, float]] = [
            # Fase 1: solo paleta, fps original (máxima calidad visual)
            ("keep", 256, 1.0),
            ("keep", 224, 1.0),
            ("keep", 192, 1.0),
            ("keep", 160, 1.0),
            ("keep", 128, 1.0),
            ("keep", 96,  1.0),
            # Fase 2: 30 fps
            ("30",   256, 1.0),
            ("30",   224, 1.0),
            ("30",   192, 1.0),
            ("30",   160, 1.0),
            ("30",   128, 1.0),
            ("30",   96,  1.0),
            # Fase 3: 25 fps
            ("25",   224, 1.0),
            ("25",   192, 1.0),
            ("25",   160, 1.0),
            ("25",   128, 1.0),
            ("25",   96,  1.0),
            # Fase 4: 22 fps
            ("22",   192, 1.0),
            ("22",   160, 1.0),
            ("22",   128, 1.0),
            ("22",   96,  1.0),
            # Fase 5: 20 fps
            ("20",   192, 1.0),
            ("20",   160, 1.0),
            ("20",   128, 1.0),
            ("20",   96,  1.0),
            ("20",   80,  1.0),
            # Fase 6: 18 fps
            ("18",   160, 1.0),
            ("18",   128, 1.0),
            ("18",   96,  1.0),
            ("18",   80,  1.0),
            # Fase 7: 15 fps
            ("15",   128, 1.0),
            ("15",   96,  1.0),
            ("15",   80,  1.0),
            ("15",   64,  1.0),
            # Fase 8: 12 fps
            ("12",   96,  1.0),
            ("12",   80,  1.0),
            ("12",   64,  1.0),
            ("12",   48,  1.0),
            # Fase 9: 10 fps
            ("10",   80,  1.0),
            ("10",   64,  1.0),
            ("10",   48,  1.0),
            ("10",   32,  1.0),
            # Fase 10: último recurso (8-6 fps)
            ("8",    48,  1.0),
            ("8",    32,  1.0),
            ("6",    32,  1.0),
            ("6",    16,  1.0),
        ]

        out_dir = self._workspace_dir(gif_path, "optimizado")
        self._archive_before_overwrite(out_dir, keep_names=[f"{gif_path.stem}_opt.gif"])
        out_path = out_dir / f"{gif_path.stem}_opt.gif"
        best_path: Optional[Path] = None
        best_mb: float = 0.0
        winning_strategy: Optional[Tuple[str, int, float]] = None

        import tempfile
        tmp_dir = Path(tempfile.mkdtemp(prefix="wkart_opt_"))

        def _run_candidate(fps: str, colors: int, scale: float,
                           label_idx: str) -> Tuple[Optional[Path], float]:
            """Ejecuta ffmpeg con los parámetros dados. Devuelve (path, size_mb)
            o (None, 0.0) si falla."""
            filters = []
            if fps != "keep":
                filters.append(f"fps={fps}")
            if scale < 1.0:
                filters.append(f"scale=iw*{scale}:ih*{scale}:flags=lanczos")
            filters.append(
                f"split[s0][s1];[s0]palettegen=max_colors={colors}:stats_mode=diff[p];"
                f"[s1][p]paletteuse=dither=sierra2_4a"
            )
            vf = ",".join(filters)
            cand = tmp_dir / f"cand_{label_idx}.gif"
            cmd = [str(self.ffmpeg_path), "-y", "-i", str(gif_path),
                   "-vf", vf, "-loop", "0", str(cand)]
            try:
                r = subprocess.run(cmd, capture_output=True, text=True,
                                   timeout=180, **_NO_WINDOW_FLAGS)
            except Exception as e:
                log(f"  Candidato {label_idx} error: {e}")
                return None, 0.0
            if r.returncode != 0 or not cand.exists():
                log(f"  Candidato {label_idx} falló (rc={r.returncode})")
                return None, 0.0
            return cand, cand.stat().st_size / (1024 * 1024)

        try:
            hit_range = False
            for idx, (fps, colors, scale) in enumerate(strategies, 1):
                candidate, size_mb = _run_candidate(fps, colors, scale, f"{idx:02d}")
                if candidate is None:
                    continue

                label = f"fps={fps}, colors={colors}, scale={scale}"
                log(f"  [{idx}/{len(strategies)}] {label} → {size_mb:.2f} MB")

                # Dentro del rango óptimo → perfecto, parar aquí
                if min_mb <= size_mb <= max_mb:
                    best_path = candidate
                    best_mb = size_mb
                    winning_strategy = (fps, colors, scale)
                    log(f"✅ Dentro del rango [{min_mb:.1f}, {max_mb:.1f}] MB en intento {idx}")
                    hit_range = True
                    break

                # Por debajo del máximo: candidato válido, guardar el mayor
                if size_mb <= max_mb and size_mb > best_mb:
                    best_mb = size_mb
                    best_path = candidate
                    winning_strategy = (fps, colors, scale)
                    # Primera vez que cabe bajo el cap → salimos a refinar.
                    # Las siguientes estrategias son de MENOR calidad, no tiene
                    # sentido seguirlas si ya cabe.
                    break

                # Por encima todavía: sigue bajando calidad
                # (no hacemos nada, el loop continúa)

            # Refinamiento: si cabe pero está por debajo de min_mb, búsqueda
            # binaria de paleta hacia arriba para acercarnos al cap sin pasarnos.
            if (not hit_range and best_path is not None and winning_strategy is not None
                    and best_mb < min_mb):
                w_fps, w_colors, w_scale = winning_strategy
                log(f"🔧 Margen libre ({best_mb:.2f} MB < {min_mb:.1f}) — "
                    f"refinando paleta hacia arriba para maximizar calidad...")
                lo, hi = w_colors, 256
                for probe in range(6):
                    if hi - lo <= 4:
                        break
                    mid = (lo + hi) // 2
                    cand, size_mb = _run_candidate(w_fps, mid, w_scale, f"ref{probe+1}")
                    if cand is None:
                        break
                    log(f"  refinado paleta={mid} → {size_mb:.2f} MB")
                    if size_mb <= max_mb:
                        if size_mb > best_mb:
                            best_mb = size_mb
                            best_path = cand
                            winning_strategy = (w_fps, mid, w_scale)
                        lo = mid
                        if min_mb <= size_mb <= max_mb:
                            log(f"✅ Refinado en rango [{min_mb:.1f}, {max_mb:.1f}] "
                                f"con paleta={mid}")
                            break
                    else:
                        hi = mid

            if hit_range or best_path is not None:
                # Salida con el mejor candidato encontrado
                shutil.copy(best_path, out_path)
                fps_w, colors_w, scale_w = winning_strategy or ("?", 0, 0.0)
                self._write_manifest(out_dir, "optimizar_tamano",
                    {"max_mb": max_mb, "min_mb": min_mb,
                     "fps": fps_w, "colors": colors_w, "scale": scale_w,
                     "resultado_mb": round(best_mb, 3),
                     "original_mb": round(original_mb, 3)},
                    archivos=[out_path], fuente=gif_path)
                self._patch_gif_trailer(out_path)
                return out_path

            log(f"❌ No se consiguió bajar de {max_mb:.2f} MB con ninguna "
                f"de las {len(strategies)} estrategias probadas.")
            log(f"   Tamaño original: {original_mb:.2f} MB — el GIF es "
                f"demasiado largo. Recorta la duración de entrada.")
            return None
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def shrink_batch_to_size_cap(self, gif_paths: List[Path],
                                 max_mb: float = 5.0,
                                 min_mb: float = 4.7,
                                 progress_cb: Optional[Callable[[str], None]] = None
                                 ) -> List[Optional[Path]]:
        """Optimiza varios fragmentos compartiendo UNA misma estrategia.

        Esto evita desincronización visual cuando los fragmentos se muestran
        como long-artwork lado a lado (si cada uno tuviera distinto fps,
        se verían fuera de sincronía). Busca la estrategia de mayor calidad
        en la que TODOS los fragmentos quepan bajo `max_mb`, y la aplica a
        todos. Luego refina paleta hacia arriba si el mayor queda por
        debajo de `min_mb`.

        Devuelve lista de rutas de salida (una por input), con None donde
        no se haya podido optimizar.
        """
        def log(msg: str):
            logger.info(msg)
            if progress_cb:
                try:
                    progress_cb(msg)
                except Exception:
                    pass

        if not self.ffmpeg_path:
            log("FFmpeg no disponible")
            return [None] * len(gif_paths)

        paths = [Path(p) for p in gif_paths if p and Path(p).exists()]
        if not paths:
            return []

        # Mismas fases que shrink_to_size_cap (ordenadas de mayor a menor calidad)
        strategies: List[Tuple[str, int, float]] = [
            ("keep", 256, 1.0), ("keep", 224, 1.0), ("keep", 192, 1.0),
            ("keep", 160, 1.0), ("keep", 128, 1.0), ("keep", 96, 1.0),
            ("30", 256, 1.0), ("30", 224, 1.0), ("30", 192, 1.0),
            ("30", 160, 1.0), ("30", 128, 1.0), ("30", 96, 1.0),
            ("25", 224, 1.0), ("25", 192, 1.0), ("25", 160, 1.0),
            ("25", 128, 1.0), ("25", 96, 1.0),
            ("22", 192, 1.0), ("22", 160, 1.0), ("22", 128, 1.0), ("22", 96, 1.0),
            ("20", 192, 1.0), ("20", 160, 1.0), ("20", 128, 1.0),
            ("20", 96, 1.0), ("20", 80, 1.0),
            ("18", 160, 1.0), ("18", 128, 1.0), ("18", 96, 1.0), ("18", 80, 1.0),
            ("15", 128, 1.0), ("15", 96, 1.0), ("15", 80, 1.0), ("15", 64, 1.0),
            ("12", 96, 1.0), ("12", 80, 1.0), ("12", 64, 1.0), ("12", 48, 1.0),
            ("10", 80, 1.0), ("10", 64, 1.0), ("10", 48, 1.0), ("10", 32, 1.0),
            ("8", 48, 1.0), ("8", 32, 1.0), ("6", 32, 1.0), ("6", 16, 1.0),
        ]

        import tempfile
        tmp_dir = Path(tempfile.mkdtemp(prefix="wkart_batch_opt_"))

        def _run_all(fps: str, colors: int, scale: float,
                     label: str) -> Optional[List[Tuple[Path, float]]]:
            """Aplica una estrategia a todos los inputs. Devuelve lista de
            (ruta_candidato, size_mb) si todos OK; None si alguno falla."""
            filters = []
            if fps != "keep":
                filters.append(f"fps={fps}")
            if scale < 1.0:
                filters.append(f"scale=iw*{scale}:ih*{scale}:flags=lanczos")
            filters.append(
                f"split[s0][s1];[s0]palettegen=max_colors={colors}:stats_mode=diff[p];"
                f"[s1][p]paletteuse=dither=sierra2_4a"
            )
            vf = ",".join(filters)
            out: List[Tuple[Path, float]] = []
            for i, src in enumerate(paths):
                cand = tmp_dir / f"{label}_{i:02d}.gif"
                cmd = [str(self.ffmpeg_path), "-y", "-i", str(src),
                       "-vf", vf, "-loop", "0", str(cand)]
                try:
                    r = subprocess.run(cmd, capture_output=True, text=True,
                                       timeout=180, **_NO_WINDOW_FLAGS)
                except Exception as e:
                    log(f"  {label} frag {i+1} error: {e}")
                    return None
                if r.returncode != 0 or not cand.exists():
                    return None
                out.append((cand, cand.stat().st_size / (1024 * 1024)))
            return out

        log(f"=== Optimización batch de {len(paths)} fragmentos a ≤{max_mb:.2f} MB (estrategia compartida) ===")

        winning_strategy: Optional[Tuple[str, int, float]] = None
        winning_results: Optional[List[Tuple[Path, float]]] = None

        try:
            # 1) Primer fit: estrategia de mayor calidad donde TODOS quepan
            for idx, (fps, colors, scale) in enumerate(strategies, 1):
                results = _run_all(fps, colors, scale, f"s{idx:02d}")
                if results is None:
                    log(f"  [{idx}/{len(strategies)}] fps={fps}, colors={colors} — falló algún fragmento")
                    continue
                max_mb_seen = max(r[1] for r in results)
                log(f"  [{idx}/{len(strategies)}] fps={fps}, colors={colors} → max fragmento: {max_mb_seen:.2f} MB")
                if max_mb_seen <= max_mb:
                    winning_strategy = (fps, colors, scale)
                    winning_results = results
                    log(f"✅ Todos los fragmentos caben bajo {max_mb:.2f} MB en intento {idx}")
                    break

            # 2) Refinamiento de paleta si hay margen
            if winning_strategy is not None and winning_results is not None:
                w_fps, w_colors, w_scale = winning_strategy
                cur_max = max(r[1] for r in winning_results)
                if cur_max < min_mb and w_colors < 256:
                    log(f"🔧 Margen libre (max={cur_max:.2f} MB < {min_mb:.1f}) — "
                        f"refinando paleta hacia arriba...")
                    lo, hi = w_colors, 256
                    for probe in range(6):
                        if hi - lo <= 4:
                            break
                        mid = (lo + hi) // 2
                        res = _run_all(w_fps, mid, w_scale, f"ref{probe+1}")
                        if res is None:
                            hi = mid
                            continue
                        mx = max(r[1] for r in res)
                        log(f"  refinado paleta={mid} → max fragmento: {mx:.2f} MB")
                        if mx <= max_mb:
                            if mx > cur_max:
                                cur_max = mx
                                winning_strategy = (w_fps, mid, w_scale)
                                winning_results = res
                            lo = mid
                            if mx >= min_mb:
                                log(f"✅ Refinado en rango [{min_mb:.1f}, {max_mb:.1f}] con paleta={mid}")
                                break
                        else:
                            hi = mid

            if winning_results is None or winning_strategy is None:
                log(f"❌ No se encontró estrategia común bajo {max_mb:.2f} MB para todos los fragmentos.")
                return [None] * len(paths)

            # 3) Copiar candidatos a carpeta "optimizado" de cada fragmento
            out_paths: List[Optional[Path]] = []
            fps_w, colors_w, scale_w = winning_strategy

            # Limpia UNA sola vez preservando TODOS los nombres de salida.
            # (Hacerlo dentro del loop borraba los fragmentos ya escritos.)
            all_out_names = [f"{src.stem}_opt.gif" for src in paths]
            dirs_cleaned: set = set()
            for src in paths:
                out_dir = self._workspace_dir(src, "optimizado")
                if out_dir in dirs_cleaned:
                    continue
                self._archive_before_overwrite(out_dir, keep_names=all_out_names)
                dirs_cleaned.add(out_dir)

            for src, (cand, size_mb) in zip(paths, winning_results):
                try:
                    out_dir = self._workspace_dir(src, "optimizado")
                    dst = out_dir / f"{src.stem}_opt.gif"
                    shutil.copy(cand, dst)
                    self._write_manifest(out_dir, "optimizar_tamano_batch",
                        {"max_mb": max_mb, "min_mb": min_mb,
                         "fps": fps_w, "colors": colors_w, "scale": scale_w,
                         "resultado_mb": round(size_mb, 3),
                         "estrategia_compartida": True,
                         "total_fragmentos": len(paths)},
                        archivos=[dst], fuente=src)
                    self._patch_gif_trailer(dst)
                    out_paths.append(dst)
                    log(f"✅ {src.name} → {dst.name} ({size_mb:.2f} MB)")
                except Exception as e:
                    log(f"❌ Error copiando {src.name}: {e}")
                    out_paths.append(None)
            return out_paths
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def interpolate_frames_rife(self, gif_path: Path, multiplier: int = 2) -> Optional[Path]:
        """Interpolación de frames con RIFE (IA). Mucho más fluido que duplicar frames.

        Requiere rife-ncnn-vulkan.exe en el directorio del proyecto.
        """
        if not self.rife_path or not self.rife_path.exists():
            logger.error("RIFE no encontrado. Descarga rife-ncnn-vulkan y colócalo junto al proyecto.")
            return None
        if not self.ffmpeg_path:
            logger.error("FFmpeg no disponible para reensamblar.")
            return None

        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            frames_in = tmp / "frames_in"
            frames_out = tmp / "frames_out"
            frames_in.mkdir()
            frames_out.mkdir()

            # 1) Extraer frames del GIF (composición correcta para disposal=2)
            try:
                with Image.open(gif_path) as img:
                    original_duration = img.info.get('duration', 100)
                    n_frames = getattr(img, 'n_frames', 1)
                    for i in range(n_frames):
                        img.seek(i)
                        composed = img.convert('RGBA')
                        composed.save(frames_in / f"{i:06d}.png", "PNG")
            except Exception as e:
                logger.error(f"Error extrayendo frames para RIFE: {e}")
                return None

            # 2) RIFE sobre la carpeta
            cmd = [str(self.rife_path),
                   "-i", str(frames_in),
                   "-o", str(frames_out),
                   "-n", str(multiplier)]
            if not self.use_gpu:
                cmd.extend(["-g", "-1"])
            try:
                logger.info(f"Ejecutando RIFE: {' '.join(cmd)}")
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=900, **_NO_WINDOW_FLAGS)
                if result.returncode != 0:
                    logger.error(f"RIFE falló: {result.stderr[:500]}")
                    return None
            except subprocess.TimeoutExpired:
                logger.error("RIFE timeout (>15 min)")
                return None
            except Exception as e:
                logger.error(f"Error ejecutando RIFE: {e}")
                return None

            # 3) Reensamblar con ffmpeg a FPS multiplicado (float para no perder precisión)
            original_fps = 1000.0 / max(1, original_duration)
            new_fps = original_fps * multiplier
            # Hueco único en el nombre para no pisar salidas previas
            import time as _t
            output_path = self._workspace_dir(gif_path, "interpolado") / f"{gif_path.stem}_RIFE{multiplier}x_{int(_t.time())}.gif"

            cmd2 = [str(self.ffmpeg_path), "-y",
                    "-framerate", f"{new_fps:.3f}",
                    "-i", str(frames_out / "%06d.png"),
                    "-vf", "split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse",
                    "-loop", "0",
                    str(output_path)]
            try:
                r2 = subprocess.run(cmd2, capture_output=True, text=True, timeout=300, **_NO_WINDOW_FLAGS)
                if r2.returncode != 0:
                    logger.error(f"FFmpeg reensamblado falló: {r2.stderr[:500]}")
                    return None
            except Exception as e:
                logger.error(f"Error en reensamblado: {e}")
                return None

            # Paso intermedio (reensamblado de frames): no parchear trailer.
            return output_path

    def optimize_gif_playback(self, gif_path: Path) -> Optional[Path]:
        """Normalize frame timing for smoother playback."""
        output_path = self._workspace_dir(gif_path, "optimizado") / f"{gif_path.stem}_optimized.gif"

        try:
            with Image.open(gif_path) as img:
                frames = []
                durations = []
                for frame in ImageSequence.Iterator(img):
                    frames.append(frame.copy())
                    durations.append(img.info.get('duration', 100))

            if not durations:
                return gif_path

            avg_duration = max(50, min(200, int(sum(durations) / len(durations))))

            frames[0].save(
                output_path,
                save_all=True,
                append_images=frames[1:],
                duration=avg_duration,
                loop=0,
                optimize=False,
            )
            # Paso intermedio: no parchear trailer.
            return output_path
        except Exception as e:
            logger.error(f"Error optimizing playback: {e}")
            return None
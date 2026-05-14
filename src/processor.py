"""
processor.py — Core image/video/GIF processing engine for WorkshopArt.

Responsibilities:
  - AI upscaling via Real-ESRGAN / Real-CUGAN (subprocess or Python bindings)
  - GIF creation and optimization: PIL multi-attempt pipeline with FFmpeg fallback
  - Steam-compliant GIF splitting for profile (5 parts) and artwork showcase (2 parts)
  - Showcase preset system: static + animated splits for various Steam panel layouts
  - Color enhancement: contrast, saturation, vibrance, sharpness, temperature
  - GIF size capping (shrink_to_size_cap) using gifski binary-search + FFmpeg ladder
  - GIF trailer patching (0x3B → 0x21) required for Steam full-size rendering
  - gifsicle LZW recompression pass for lossless size reduction
"""
import sys
import os
import shutil
import platform
import subprocess
import logging
from pathlib import Path
from typing import Optional, List, Tuple, Callable
from PIL import Image, ImageSequence, ImageEnhance, ImageFilter
import numpy as np
from tqdm import tqdm
from config import Config
from models import ModelManager
from analyzers import ContentAnalyzer

# Hide subprocess console windows on Windows
_NO_WINDOW_FLAGS = {'creationflags': subprocess.CREATE_NO_WINDOW} if platform.system() == 'Windows' else {}


logger = logging.getLogger("WorkshopArtPRO.processor")

class SteamProcessor:
    """Main processor for images, video, and GIFs destined for Steam Workshop uploads."""

    def __init__(self, config: Config):
        self.config = config
        self.model_manager = ModelManager(Path(config.get('paths.models')))
        self.content_analyzer = ContentAnalyzer()
        self.use_gpu = config.get('gpu.use_gpu', True)
        self.gpu_id = config.get('gpu.gpu_id', 0)
        
        if getattr(sys, 'frozen', False):
            # PyInstaller sets sys.frozen; executables live next to bundled assets
            self.base_path = Path(sys.executable).parent
        else:
            self.base_path = Path.cwd()
        
        logger.info(f"🔍 Base path detectado: {self.base_path}")
        
        # Rutas de ejecutables
        self.ffmpeg_path = self._find_executable("ffmpeg")
        self.gifski_path = self._find_executable("gifski")
        self.gifsicle_path = self._find_executable("gifsicle")
        self.realesrgan_path = self._find_executable("realesrgan-ncnn-vulkan")
        self.realcugan_path = self._find_executable("realcugan-ncnn-vulkan")

        logger.info(f"FFmpeg: {self.ffmpeg_path}")
        logger.info(f"gifski: {self.gifski_path or 'no encontrado (opcional)'}")
        logger.info(f"gifsicle: {self.gifsicle_path or 'no encontrado (se descargará al usar)'}")
        logger.info(f"Real-ESRGAN: {self.realesrgan_path}")
        logger.info(f"Real-CUGAN: {self.realcugan_path}")

        self._last_split_error = ""

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
        """Remove processing suffixes and part-numbering from a filename stem to recover the original base name."""
        import re
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
        """Return (and create) a category subdirectory inside the workspace root for source."""
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
        """Locate a bundled or system-installed executable by name.
        Checks SteamWorkshopAppData/, base dir, _internal/, cwd, then PATH."""
        ext = ".exe" if platform.system() == "Windows" else ""
        filename = f"{name}{ext}"

        search_paths = [
            self.base_path / "SteamWorkshopAppData" / filename,  # preferred bundle location
            self.base_path / filename,                             # legacy: next to the exe
            self.base_path / "_internal" / filename,               # PyInstaller _internal dir
            Path.cwd() / filename,
        ]

        for path in search_paths:
            if path.exists():
                logger.info(f"✅ Encontrado {name} en: {path}")
                return path

        # Fall back to system PATH (e.g. ffmpeg installed globally)
        system_path = shutil.which(name)
        if system_path:
            logger.info(f"✅ Encontrado {name} en PATH: {system_path}")
            return Path(system_path)

        logger.error(f"❌ No se encontró {name}")
        return None

    def check_gpu_available(self, force: bool = False) -> Tuple[bool, str]:
        """Return (available, description) for the best detected GPU, using a cached result.
        Pass force=True to bypass the cache and re-probe (e.g. after driver changes)."""
        if self._gpu_cache is not None and not force:
            return self._gpu_cache
        result = self._check_gpu_uncached()
        self._gpu_cache = result
        return result

    def _check_gpu_uncached(self) -> Tuple[bool, str]:
        """Probe GPU availability: tries Real-ESRGAN -h, then wmic on Windows."""
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
                                        # Intentar obtener VRAM via wmic AdapterRAM
                                        try:
                                            vram_res = subprocess.run(
                                                ['wmic', 'path', 'win32_VideoController', 'get', 'AdapterRAM'],
                                                capture_output=True, text=True, timeout=5, **_NO_WINDOW_FLAGS
                                            )
                                            for vline in vram_res.stdout.strip().split('\n'):
                                                try:
                                                    vram_bytes = int(vline.strip())
                                                    if vram_bytes > 0:
                                                        vram_gb = vram_bytes / (1024 ** 3)
                                                        return True, f"AMD: {clean_line} ({vram_gb:.0f} GB VRAM)"
                                                except ValueError:
                                                    pass
                                        except Exception:
                                            pass
                                        return True, f"AMD: {clean_line}"
                            return True, "AMD GPU detectada"

                        # Buscar NVIDIA
                        elif 'nvidia' in gpu_info or 'geforce' in gpu_info:
                            lines = result.stdout.strip().split('\n')
                            for line in lines:
                                if 'nvidia' in line.lower() or 'geforce' in line.lower():
                                    clean_line = line.strip()
                                    if clean_line and clean_line != "Name":
                                        try:
                                            import GPUtil  # optional; not always installed
                                            gpus = GPUtil.getGPUs()
                                            if gpus:
                                                vram_gb = gpus[0].memoryTotal / 1024  # memoryTotal is MB
                                                return True, f"NVIDIA: {clean_line} ({vram_gb:.0f} GB VRAM)"
                                        except Exception:
                                            pass
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

    def check_gifski(self) -> bool:
        """Verificar disponibilidad de gifski (encoder GIF de alta calidad)"""
        return self.gifski_path is not None and self.gifski_path.exists()
    
    def extract_gif_frames(self, gif_path: Path, output_dir: Path) -> Tuple[Optional[List[Path]], Optional[int]]:
        """Extract all GIF frames as RGB PNGs into output_dir.
        Returns (list_of_frame_paths, avg_frame_duration_ms), or (None, None) on failure."""
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

                    duration = gif.info.get('duration', 100)  # milliseconds per frame
                    durations.append(duration)

                avg_duration = sum(durations) / len(durations) if durations else 100
                return frames, int(avg_duration)
        except Exception as e:
            logger.error(f"Error extrayendo frames: {e}")
            return None, None
    
    def extract_video_frames(self, video_path: Path, output_dir: Path) -> Optional[float]:
        """Extract all video frames as RGB PNGs using moviepy. Returns the source FPS, or None on failure."""
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
        """Upscale all PNG frames in input_dir using Real-ESRGAN or Real-CUGAN.
        Tries Python bindings first (faster, no subprocess), then falls back to the CLI binary.
        Retries with CPU if the GPU device is invalid. Returns sorted list of output paths or None."""
        output_dir.mkdir(exist_ok=True)

        # Verificar que hay frames de entrada
        input_frames = list(input_dir.glob("*.png"))
        if not input_frames:
            if progress_callback:
                progress_callback("Error: No hay frames de entrada", 0)
            return None

        # Strip any human-readable description appended by the UI (e.g. "realesrgan-x4plus - Anime")
        clean_model_name = model_name.split(" - ")[0].split(" ")[0]

        model_info = self.model_manager.get_model_info(clean_model_name)
        engine = model_info.get("engine", "realesrgan")

        gpu_id = "0" if use_gpu else "-1"  # ncnn uses -1 to force CPU

        # --- Fast path: Python bindings (realesrgan-ncnn-py, PRO) ---
        if engine != "realcugan":
            try:
                from realesrgan_ncnn_py import Realesrgan as _RealESRGAN
                _MODEL_IDS = {
                    "realesr-animevideov3-x4": 0, "realesr-animevideov3-x3": 0,
                    "realesr-animevideov3-x2": 0, "realesrgan-x4plus": 1,
                    "realesrgan-x4plus-anime": 2, "realesrnet-x4plus": 3,
                    "realesr-general-x4v3": 0,
                }
                _model_id = _MODEL_IDS.get(clean_model_name, 0)
                _gpu_id = 0 if use_gpu else -1
                _upscaler = _RealESRGAN(gpuid=_gpu_id, model=_model_id)
                upscaled: List[Path] = []
                total = len(input_frames)
                for i, fp in enumerate(sorted(input_frames)):
                    with Image.open(fp) as _img:
                        result = _upscaler.process_pil(_img)
                    out_fp = output_dir / fp.name
                    result.save(out_fp)
                    upscaled.append(out_fp)
                    if progress_callback:
                        progress_callback(
                            f"Upscaling frame {i+1}/{total} (bindings)",
                            int((i + 1) / total * 80)
                        )
                logger.info(f"upscale via Python bindings: {len(upscaled)} frames")
                return upscaled or None
            except ImportError:
                pass  # bindings not installed; fall through to subprocess
            except Exception as e:
                logger.warning(f"realesrgan-ncnn-py falló ({e}), usando subprocess")

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

            models_path = exe_path.parent / model_dir  # model dir must be relative to the binary

            cmd = [
                str(exe_path),
                "-i", str(input_dir),
                "-o", str(output_dir),
                "-s", scale,       # upscale factor
                "-n", noise,       # denoising level (0 = off)
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
                "-n", clean_model_name,  # model name without extension (.bin/.param)
                "-s", "4",               # fixed 4x upscale for Real-ESRGAN models
                "-f", "png",
                "-g", gpu_id,
            ]
            working_dir = exe_path.parent  # ncnn loads model files relative to cwd
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

            # Dynamic timeout: 5 min base + 5 s/frame, minimum 10 min (1300 frames ≈ 2 h)
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
                tmp = Path(tempfile.mktemp(suffix=".zip"))
                with open(tmp, "wb") as f:
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

    def split_gif_for_steam(self, gif_path: Path) -> bool:
        """Split a GIF into 5 equal-width parts for Steam Workshop profile uploads.
        Uses gifski binary-search quality as primary encoder, FFmpeg as fallback.
        Each part must be ≤ 5 MiB to comply with Steam's per-file size limit."""
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
            
            # Fragmentar: gifski primary (binary-search quality), ffmpeg fallback
            success = True
            created_parts = []
            MAX_BYTES = 5 * 1024 * 1024 - 16 * 1024  # 16 KiB headroom below Steam's hard 5 MiB limit
            _use_gifski = self.check_gifski()

            _orig_fps = 25
            try:
                with Image.open(gif_path) as _fps_img:
                    _dur = _fps_img.info.get('duration', 40) or 40
                    _orig_fps = max(1, int(round(1000.0 / _dur)))
            except Exception:
                pass

            import tempfile
            _tmp = Path(tempfile.mkdtemp(prefix="wkart_steam_"))
            _gifski_done = False
            try:
                # ── gifski: shared fps+quality for ALL 5 parts ───────────────
                if _use_gifski:
                    # Outer loop: descend fps tiers until ALL 5 parts fit under MAX_BYTES
                    for fps_cap in [None, 24, 20, 15, 12, 10, 8, 6, 4, 3]:
                        _fps_a = str(fps_cap) if fps_cap else str(_orig_fps)

                        # Extract PNG frames for all 5 parts at this fps tier
                        _fds: dict = {}
                        _ex_ok = True
                        for i in range(5):
                            left = i * section_width
                            _vf = f"crop={section_width}:{height}:{left}:0"
                            if fps_cap:
                                _vf = f"fps={fps_cap}," + _vf
                            fd = _tmp / f"fd_{fps_cap or 0}_p{i+1}"
                            shutil.rmtree(fd, ignore_errors=True)
                            fd.mkdir()
                            r_ex = subprocess.run(
                                [str(self.ffmpeg_path), "-y", "-i", str(gif_path),
                                 "-vf", _vf, str(fd / "frame%06d.png")],
                                capture_output=True, encoding='utf-8',
                                errors='replace', timeout=120, **_NO_WINDOW_FLAGS)
                            if r_ex.returncode != 0 or not any(fd.glob("frame*.png")):
                                logger.warning(f"   gifski/extract parte {i+1} fps={_fps_a}: rc={r_ex.returncode}")
                                _ex_ok = False
                                break
                            _fds[i] = fd

                        if not _ex_ok:
                            for fd in _fds.values():
                                shutil.rmtree(fd, ignore_errors=True)
                            continue

                        # Binary-search highest gifski quality where ALL 5 parts fit ≤ MAX_BYTES.
                        # Converges in ≤ ceil(log2(85)) ≈ 7 iterations.
                        q_lo, q_hi = 10, 95
                        _best_q = None
                        _best_baks: dict = {}
                        _best_sizes: dict = {}

                        while q_lo <= q_hi:
                            q = (q_lo + q_hi) // 2
                            _res: dict = {}
                            _all_fit = True
                            for i in range(5):
                                out_path = output_dir / f"{gif_path.stem}_part_{i+1}.gif"
                                fd = _fds[i]
                                r = subprocess.run(
                                    [str(self.gifski_path), "--fps", _fps_a,
                                     "--quality", str(q),  # 1-100; higher = better visual quality but larger file
                                     "--repeat", "0",       # 0 = loop forever
                                     "-o", str(out_path), str(fd / "frame*.png")],
                                    capture_output=True, encoding='utf-8',
                                    errors='replace', timeout=180, **_NO_WINDOW_FLAGS)
                                if r.returncode != 0 or not out_path.exists():
                                    logger.warning(f"   gifski parte {i+1} q={q} rc={r.returncode}")
                                    _all_fit = False
                                    break
                                sz = out_path.stat().st_size
                                logger.info(f"   gifski parte {i+1} q={q} fps={_fps_a} → {sz/1024/1024:.2f} MB")
                                _res[i] = (out_path, sz)
                                if sz > MAX_BYTES:
                                    _all_fit = False
                                    break

                            if _all_fit and len(_res) == 5:
                                _best_q = q
                                for i, (path, sz) in _res.items():
                                    bak = path.with_suffix("._gbest")
                                    shutil.copy(path, bak)
                                    _best_baks[i] = bak
                                    _best_sizes[i] = sz
                                q_lo = q + 1
                            else:
                                q_hi = q - 1

                        for fd in _fds.values():
                            shutil.rmtree(fd, ignore_errors=True)

                        if _best_q is not None:
                            for i in range(5):
                                out_path = output_dir / f"{gif_path.stem}_part_{i+1}.gif"
                                bak = _best_baks.get(i)
                                if bak and bak.exists():
                                    shutil.copy(bak, out_path)
                                    try: bak.unlink()
                                    except OSError: pass
                                self._patch_gif_trailer(out_path)
                                size_mb = _best_sizes[i] / (1024 * 1024)
                                created_parts.append({"part": i+1, "path": out_path, "size": size_mb})
                                logger.info(f"✅ Parte {i+1}: {size_mb:.2f} MB [gifski fps={_fps_a} q={_best_q}]")
                            _gifski_done = True
                            break

                        for bak in _best_baks.values():
                            try: bak.unlink()
                            except OSError: pass

                # ── ffmpeg fallback ───────────────────────────────────────────
                if not _gifski_done:
                    for i in range(5):
                        left = i * section_width
                        output_path = output_dir / f"{gif_path.stem}_part_{i+1}.gif"
                        logger.info(f"✂️ Creando parte {i+1}/5: {output_path.name}")
                        cmd = [
                            str(self.ffmpeg_path), "-i", str(gif_path),
                            "-vf", (
                                f"crop={section_width}:{height}:{left}:0,"   # crop to this panel's column
                                f"split[s0][s1];"                              # fork stream for 2-pass palette
                                f"[s0]palettegen=max_colors=256"
                                f":reserve_transparent=1"                      # keep 1 palette slot for transparency
                                f":stats_mode=full[p];"                        # analyse all frames for optimal palette
                                f"[s1][p]paletteuse=dither=sierra2_4a"        # sierra2_4a: best dither for animation
                                f":diff_mode=rectangle"                        # only dither changed rectangular regions
                            ),
                            "-y", str(output_path)
                        ]
                        try:
                            result = subprocess.run(
                                cmd, capture_output=True, encoding='utf-8',
                                errors='replace', timeout=60, **_NO_WINDOW_FLAGS)
                            if result.returncode != 0:
                                logger.error(f"❌ Error en parte {i+1}: {result.stderr[-200:]}")
                                success = False
                                break
                        except Exception as e:
                            logger.error(f"❌ Excepción en parte {i+1}: {e}")
                            success = False
                            break

                        if not output_path.exists():
                            logger.error(f"❌ Parte {i+1}: no se creó el archivo")
                            success = False
                            break
                        self._patch_gif_trailer(output_path)
                        size_mb = output_path.stat().st_size / (1024 * 1024)
                        created_parts.append({"part": i+1, "path": output_path, "size": size_mb})
                        logger.info(f"✅ Parte {i+1}: {size_mb:.2f} MB [ffmpeg]")
            finally:
                shutil.rmtree(_tmp, ignore_errors=True)
            
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

    def _gifski_optimal(self, frame_glob: str, out_path: Path,
                        fps_arg: str, max_bytes: int,
                        q_lo: int = 10, q_hi: int = 95) -> Optional[tuple]:
        """Binary-search the highest gifski quality that produces a file ≤ max_bytes.

        Returns (quality, file_size_bytes) or None if even q_lo is too large.
        Converges in ≤ ceil(log2(q_hi - q_lo + 1)) ≈ 7 iterations.
        """
        # The binary search may overwrite out_path with a "too large" result after
        # finding a good one.  Save a copy each time we beat the budget so we can
        # restore the real best file at the end.
        best = None
        _bak = out_path.with_suffix("._gbest")
        try:
            while q_lo <= q_hi:
                q = (q_lo + q_hi) // 2
                r = subprocess.run(
                    [str(self.gifski_path),
                     "--fps", fps_arg,
                     "--quality", str(q),
                     "--repeat", "0",
                     "-o", str(out_path),
                     frame_glob],
                    capture_output=True, encoding='utf-8', errors='replace',
                    timeout=180, **_NO_WINDOW_FLAGS,
                )
                if r.returncode != 0 or not out_path.exists():
                    logger.warning(f"   gifski q={q} rc={r.returncode}")
                    q_hi = q - 1
                    continue
                size = out_path.stat().st_size
                logger.info(f"   gifski q={q} fps={fps_arg} → {size / 1024 / 1024:.2f} MiB")
                if size <= max_bytes:
                    best = (q, size)
                    shutil.copy(out_path, _bak)  # preserve this good result
                    q_lo = q + 1
                else:
                    q_hi = q - 1
        finally:
            if best is not None and _bak.exists():
                shutil.copy(_bak, out_path)  # restore actual best file
            try:
                _bak.unlink()
            except OSError:
                pass
        return best

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
        forced_height = self.config.get('artwork_showcase.height', 0)
        MAX_BYTES = 5 * 1024 * 1024 - 16 * 1024  # 16 KiB safety margin below Steam's 5 MiB limit
        STEAM_HARD_MAX = 5 * 1024 * 1024

        logger.info(f"🎨 Fragmentando para Artwork Showcase: {gif_path}")

        try:
            with Image.open(gif_path) as img:
                orig_w, orig_h = img.size
                orig_duration = img.info.get('duration', 100) or 100
            orig_fps = 1000.0 / max(1, orig_duration)
            logger.info(f"📐 Origen: {orig_w}x{orig_h} @ ~{orig_fps:.2f}fps")

            if forced_height and forced_height > 0:
                target_height = int(forced_height)
            else:
                # Preserve aspect ratio, scaling to the combined target width
                target_height = max(1, round(orig_h * total_width / max(1, orig_w)))
            if target_height % 2 == 1:
                target_height += 1  # keep even height; some codecs require it
            logger.info(f"📐 Target: {main_width}+{side_width}={total_width} × {target_height}")

            parts_config = [
                {"name": "artwork_main", "width": main_width, "left": 0},
                {"name": "artwork_side", "width": side_width, "left": main_width},
            ]

            _use_gifski = self.check_gifski()
            logger.info(f"🎞️  Encoder: {'gifski + binary-search quality' if _use_gifski else 'ffmpeg'}")

            # gifski: iterate fps tiers, binary-search quality at each tier to
            # find the HIGHEST quality that still fits under MAX_BYTES.
            # This maximises visual quality instead of the linear ladder which
            # often overshoots and wastes available budget.
            gifski_fps_tiers = [None, 24, 20, 15, 12, 10, 8, 6, 4, 3] if _use_gifski else []

            # FFmpeg fallback: try (colors, fps_cap) pairs from highest to lowest quality
            # until both parts fit under MAX_BYTES.
            ffmpeg_ladder = [
                (256, None),
                (256, 24),
                (192, 24),
                (160, 20),
                (128, 20),
                ( 96, 15),
                ( 64, 12),
                ( 64,  8),
                ( 48,  8),
                ( 32,  6),
                ( 24,  5),
                ( 16,  4),
                ( 16,  3),
            ]

            created_parts = []
            success = True
            self._last_split_error = ""

            # ── gifski: shared fps+quality for ALL parts ─────────────────────
            # Both parts are tested at each candidate fps+quality so they always
            # share the same fps — otherwise the two panels desync during playback.
            _gifski_done = False
            if _use_gifski:
                for fps_cap in gifski_fps_tiers:
                    _fps_arg = str(int(fps_cap)) if fps_cap else str(max(1, int(orig_fps)))
                    fps_filter = f"fps={fps_cap}," if fps_cap else ""

                    # Extract frames for every part at this fps tier
                    _fds = {}
                    _ex_ok = True
                    for part in parts_config:
                        _tmp = "_ga" if part["left"] == 0 else "_gb"
                        fd = output_dir / _tmp
                        shutil.rmtree(fd, ignore_errors=True)
                        fd.mkdir(parents=True, exist_ok=True)
                        vf = (f"{fps_filter}"
                              f"scale={total_width}:{target_height}:flags=lanczos,"
                              f"crop={part['width']}:{target_height}:{part['left']}:0")
                        r = subprocess.run(
                            [str(self.ffmpeg_path), "-i", str(gif_path),
                             "-vf", vf, "-y", str(fd / "frame%06d.png")],
                            capture_output=True, encoding='utf-8', errors='replace',
                            timeout=120, **_NO_WINDOW_FLAGS)
                        if r.returncode != 0 or not any(fd.glob("frame*.png")):
                            logger.warning(f"   gifski/extract {part['name']} fps={_fps_arg}: rc={r.returncode}")
                            _ex_ok = False
                            break
                        _fds[part["name"]] = fd

                    if not _ex_ok:
                        for fd in _fds.values():
                            shutil.rmtree(fd, ignore_errors=True)
                        continue

                    # Binary-search shared quality where ALL parts fit under MAX_BYTES
                    q_lo, q_hi = 10, 95
                    _best_q = None
                    _best_baks: dict = {}
                    _best_sizes: dict = {}

                    while q_lo <= q_hi:
                        q = (q_lo + q_hi) // 2
                        _res = {}
                        _all_fit = True
                        for part in parts_config:
                            out_path = output_dir / f"{gif_path.stem}_{part['name']}.gif"
                            fd = _fds[part["name"]]
                            r = subprocess.run(
                                [str(self.gifski_path), "--fps", _fps_arg,
                                 "--quality", str(q), "--repeat", "0",
                                 "-o", str(out_path), str(fd / "frame*.png")],
                                capture_output=True, encoding='utf-8', errors='replace',
                                timeout=180, **_NO_WINDOW_FLAGS)
                            if r.returncode != 0 or not out_path.exists():
                                logger.warning(f"   gifski {part['name']} q={q} rc={r.returncode}")
                                _all_fit = False
                                break
                            sz = out_path.stat().st_size
                            logger.info(f"   gifski {part['name']} q={q} fps={_fps_arg} → {sz/1024/1024:.2f} MiB")
                            _res[part["name"]] = (out_path, sz)
                            if sz > MAX_BYTES:
                                _all_fit = False
                                break

                        if _all_fit and len(_res) == len(parts_config):
                            _best_q = q
                            for name, (path, sz) in _res.items():
                                bak = path.with_suffix("._gbest")
                                shutil.copy(path, bak)
                                _best_baks[name] = bak
                                _best_sizes[name] = sz
                            q_lo = q + 1
                        else:
                            q_hi = q - 1

                    # Cleanup frame dirs
                    for fd in _fds.values():
                        shutil.rmtree(fd, ignore_errors=True)

                    if _best_q is not None:
                        for part in parts_config:
                            name = part["name"]
                            out_path = output_dir / f"{gif_path.stem}_{name}.gif"
                            bak = _best_baks.get(name)
                            if bak and bak.exists():
                                shutil.copy(bak, out_path)
                                try: bak.unlink()
                                except OSError: pass
                            self._patch_gif_trailer(out_path)
                            size_mb = _best_sizes[name] / (1024 * 1024)
                            created_parts.append({"name": name, "path": out_path,
                                                  "size": size_mb, "engine": "gifski"})
                            logger.info(f"✅ {name}: {size_mb:.2f} MiB [gifski fps={_fps_arg} q={_best_q}]")
                        _gifski_done = True
                        break

                    for bak in _best_baks.values():
                        try: bak.unlink()
                        except OSError: pass

            # ── ffmpeg fallback: per-part (only if gifski didn't cover all) ──
            if not _gifski_done:
                for part in parts_config:
                    out_path = output_dir / f"{gif_path.stem}_{part['name']}.gif"
                    chosen = None
                    last_err = ""
                    for colors, fps_cap in ffmpeg_ladder:
                        fps_part = f"fps={fps_cap}," if fps_cap else ""
                        vf = (
                            f"{fps_part}"
                            f"scale={total_width}:{target_height}:flags=lanczos,"  # resize full canvas before crop
                            f"crop={part['width']}:{target_height}:{part['left']}:0,"  # extract this panel
                            f"split[s0][s1];"                                           # 2-pass palette
                            f"[s0]palettegen=max_colors={colors}:stats_mode=full:reserve_transparent=1[p];"
                            f"[s1][p]paletteuse=dither=sierra2_4a:diff_mode=rectangle"
                        )
                        cmd = [str(self.ffmpeg_path), "-i", str(gif_path),
                               "-vf", vf, "-loop", "0", "-y", str(out_path)]
                        logger.info(f"✂️ {part['name']}: colors={colors} fps={fps_cap or 'orig'}")
                        try:
                            result = subprocess.run(cmd, capture_output=True,
                                                    encoding='utf-8', errors='replace',
                                                    timeout=180, **_NO_WINDOW_FLAGS)
                            if result.returncode != 0:
                                last_err = (result.stderr or "")[-400:]
                                logger.warning(f"   ffmpeg rc={result.returncode}: {last_err[-150:]}")
                                continue
                            if not out_path.exists():
                                last_err = "ffmpeg no creó el archivo"
                                continue
                            size = out_path.stat().st_size
                            logger.info(f"   → {size/1024/1024:.2f} MiB")
                            if size <= MAX_BYTES:
                                chosen = {"engine": "ffmpeg", "colors": colors,
                                          "fps": fps_cap, "size": size}
                                break
                        except subprocess.TimeoutExpired:
                            last_err = "timeout"
                            continue
                        except Exception as e:
                            last_err = str(e)
                            continue

                    if chosen is None:
                        logger.error(f"❌ {part['name']}: no se pudo generar. último error: {last_err}")
                        self._last_split_error = f"{part['name']}: {last_err}"
                        success = False
                        break

                    self._patch_gif_trailer(out_path)
                    size_mb = chosen["size"] / (1024 * 1024)
                    created_parts.append({"name": part['name'], "path": out_path,
                                          "size": size_mb, "engine": chosen["engine"]})
                    logger.info(f"✅ {part['name']}: {size_mb:.2f} MiB [ffmpeg]")

            if success and len(created_parts) == 2:
                self._write_manifest(output_dir, "fragmentar_artwork_showcase",
                    {"main_width": main_width, "side_width": side_width, "height": target_height,
                     "partes": [{"name": p['name'], "engine": p['engine']} for p in created_parts]},
                    archivos=[p['path'] for p in created_parts],
                    fuente=_artwork_src)
                total_size = sum(p['size'] for p in created_parts)
                logger.info(f"✅ Fragmentación Artwork Showcase completada! Total: {total_size:.2f} MiB")
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
                    vf = (
                        f"scale={total_w}:{fixed_h}"
                        f":force_original_aspect_ratio=increase"   # scale up so neither dimension is smaller than target
                        f":flags=lanczos+accurate_rnd+full_chroma_int,"  # high-quality resize flags
                        f"crop={total_w}:{fixed_h},"               # trim overflow from force_original_aspect_ratio
                        f"crop={w}:{fixed_h}:{left}:0"             # extract this panel
                    )
                else:
                    vf = (
                        f"scale={total_w}:-2"                       # -2 = preserve aspect ratio, even height
                        f":flags=lanczos+accurate_rnd+full_chroma_int,"
                        f"crop={w}:ih:{left}:0"                     # ih = input height (unchanged)
                    )
                cmd = [str(self.ffmpeg_path), "-i", str(image_path),
                       "-vf", vf, "-q:v", "2",  # JPEG quality scale 2 ≈ ~95% quality
                       "-y", str(out_path)]
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

    # ---- Showcase preset registry (layouts verified on Steam forums 2025) ----
    # Each preset defines:
    #   parts: list of (name, width_px, left_offset_px) crop segments from the scaled source
    #   total_w: width to scale the source to before cropping
    #   fixed_h: forced height in pixels (None = preserve source aspect ratio)
    #   upload_hint: recommended upload mode ("artwork" / "screenshot" / "workshop")
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

            ffmpeg_ladder = [
                (256, None), (256, 24), (192, 24), (160, 20),
                (128, 20), (96, 15), (64, 12),
            ]

            _use_gifski = self.check_gifski()
            _orig_fps = 25
            try:
                with Image.open(gif_path) as _fps_img:
                    _dur = _fps_img.info.get('duration', 40) or 40
                    _orig_fps = max(1, int(round(1000.0 / _dur)))
            except Exception:
                pass

            import tempfile
            _tmp = Path(tempfile.mkdtemp(prefix="wkart_showcase_"))
            created = []
            _gifski_done = False
            try:
                # ── gifski: shared fps+quality for ALL parts ─────────────────
                if _use_gifski:
                    for fps_cap in [None, 24, 20, 15, 12, 10, 8, 6, 4, 3]:
                        _fps_a = str(fps_cap) if fps_cap else str(_orig_fps)

                        # Extract frames for every part at this fps tier
                        _fds: dict = {}
                        _ex_ok = True
                        for (name, w, left) in parts_cfg:
                            if fixed_h:
                                _sc = (f"scale={total_w}:{target_h}"
                                       f":force_original_aspect_ratio=increase:flags=lanczos,"
                                       f"crop={total_w}:{target_h}")
                                _cr = f"crop={w}:{target_h}:{left}:0"
                            else:
                                _sc = f"scale={total_w}:-2:flags=lanczos"
                                _cr = f"crop={w}:ih:{left}:0"
                            _vf = (f"fps={fps_cap}," if fps_cap else "") + f"{_sc},{_cr}"
                            fd = _tmp / f"fd_{fps_cap or 0}_{name}"
                            shutil.rmtree(fd, ignore_errors=True)
                            fd.mkdir()
                            r_ex = subprocess.run(
                                [str(self.ffmpeg_path), "-y", "-i", str(gif_path),
                                 "-vf", _vf, str(fd / "frame%06d.png")],
                                capture_output=True, encoding='utf-8',
                                errors='replace', timeout=180, **_NO_WINDOW_FLAGS)
                            if r_ex.returncode != 0 or not any(fd.glob("frame*.png")):
                                logger.warning(f"   gifski/extract {name} fps={_fps_a}: rc={r_ex.returncode}")
                                _ex_ok = False
                                break
                            _fds[name] = fd

                        if not _ex_ok:
                            for fd in _fds.values():
                                shutil.rmtree(fd, ignore_errors=True)
                            continue

                        # Binary-search shared quality where ALL parts fit
                        q_lo, q_hi = 10, 95
                        _best_q = None
                        _best_baks: dict = {}
                        _best_sizes: dict = {}

                        while q_lo <= q_hi:
                            q = (q_lo + q_hi) // 2
                            _res: dict = {}
                            _all_fit = True
                            for (name, w, left) in parts_cfg:
                                out_path = output_dir / f"{gif_path.stem}_{name}.gif"
                                fd = _fds[name]
                                r = subprocess.run(
                                    [str(self.gifski_path), "--fps", _fps_a,
                                     "--quality", str(q), "--repeat", "0",
                                     "-o", str(out_path), str(fd / "frame*.png")],
                                    capture_output=True, encoding='utf-8',
                                    errors='replace', timeout=180, **_NO_WINDOW_FLAGS)
                                if r.returncode != 0 or not out_path.exists():
                                    logger.warning(f"   gifski {name} q={q} rc={r.returncode}")
                                    _all_fit = False
                                    break
                                sz = out_path.stat().st_size
                                logger.info(f"   gifski {name} q={q} fps={_fps_a} → {sz/1024/1024:.2f} MiB")
                                _res[name] = (out_path, sz)
                                if sz > MAX_BYTES:
                                    _all_fit = False
                                    break

                            if _all_fit and len(_res) == len(parts_cfg):
                                _best_q = q
                                for name, (path, sz) in _res.items():
                                    bak = path.with_suffix("._gbest")
                                    shutil.copy(path, bak)
                                    _best_baks[name] = bak
                                    _best_sizes[name] = sz
                                q_lo = q + 1
                            else:
                                q_hi = q - 1

                        for fd in _fds.values():
                            shutil.rmtree(fd, ignore_errors=True)

                        if _best_q is not None:
                            for (name, w, left) in parts_cfg:
                                out_path = output_dir / f"{gif_path.stem}_{name}.gif"
                                bak = _best_baks.get(name)
                                if bak and bak.exists():
                                    shutil.copy(bak, out_path)
                                    try: bak.unlink()
                                    except OSError: pass
                                self._patch_gif_trailer(out_path)
                                sz = _best_sizes[name]
                                created.append({"name": name, "path": out_path,
                                                "size": sz/1024/1024,
                                                "colors": _best_q, "fps_cap": fps_cap})
                                logger.info(f"✅ {name}: {sz/1024/1024:.2f} MiB "
                                            f"[gifski fps={_fps_a} q={_best_q}]")
                            _gifski_done = True
                            break

                        for bak in _best_baks.values():
                            try: bak.unlink()
                            except OSError: pass

                # ── ffmpeg fallback: per-part ─────────────────────────────────
                if not _gifski_done:
                    for (name, w, left) in parts_cfg:
                        out_path = output_dir / f"{gif_path.stem}_{name}.gif"
                        chosen = None
                        last_err = ""
                        for colors, fps_cap in ffmpeg_ladder:
                            fps_part = f"fps={fps_cap}," if fps_cap else ""
                            if fixed_h:
                                scale = (f"scale={total_w}:{target_h}"
                                         f":force_original_aspect_ratio=increase"
                                         f":flags=lanczos+accurate_rnd+full_chroma_int,"
                                         f"crop={total_w}:{target_h}")
                                crop = f"crop={w}:{target_h}:{left}:0"
                            else:
                                scale = (f"scale={total_w}:-2"
                                         f":flags=lanczos+accurate_rnd+full_chroma_int")
                                crop = f"crop={w}:ih:{left}:0"
                            filter_complex = (
                                f"[0:v]{fps_part}{scale},{crop},split[a][b];"
                                f"[a]palettegen=max_colors={colors}:stats_mode=full"
                                f":reserve_transparent=1[p];"
                                f"[b][p]paletteuse=dither=sierra2_4a:diff_mode=rectangle"
                            )
                            cmd = [str(self.ffmpeg_path), "-i", str(gif_path),
                                   "-filter_complex", filter_complex, "-loop", "0",
                                   "-y", str(out_path)]
                            try:
                                r = subprocess.run(cmd, capture_output=True,
                                                   encoding='utf-8', errors='replace',
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
                            logger.error(
                                f"❌ {name}: no generado ≤ {STEAM_HARD_MAX/1024/1024:.1f} MiB. {last_err}")
                            return False
                        self._patch_gif_trailer(out_path)
                        info, fc, sz = chosen
                        created.append({"name": name, "path": out_path,
                                        "size": sz/1024/1024, "colors": info, "fps_cap": fc})
                        logger.info(f"✅ {name}: {sz/1024/1024:.2f} MiB [ffmpeg fps={fc or 'orig'}]")
            finally:
                shutil.rmtree(_tmp, ignore_errors=True)

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
                                transparency=0   # explicit 0 avoids PIL transparency artefacts
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
                
                frame_multiplier = int(60 / current_fps)
                logger.info(f"🔢 Multiplicador de frames: {frame_multiplier}")

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

        # Quality ladder: (fps, max_colors, scale_factor), ordered highest→lowest quality.
        # scale is always 1.0 — resizing individual fragments would desync the long-artwork
        # layout on the Steam profile. Only fps and palette depth are reduced.
        strategies: List[Tuple[str, int, float]] = [
            # Phase 1: palette reduction only, original fps (maximum visual quality)
            ("keep", 256, 1.0),
            ("keep", 224, 1.0),
            ("keep", 192, 1.0),
            ("keep", 160, 1.0),
            ("keep", 128, 1.0),
            ("keep", 96,  1.0),
            # Phase 2: 30 fps
            ("30",   256, 1.0),
            ("30",   224, 1.0),
            ("30",   192, 1.0),
            ("30",   160, 1.0),
            ("30",   128, 1.0),
            ("30",   96,  1.0),
            # Phase 3: 25 fps
            ("25",   224, 1.0),
            ("25",   192, 1.0),
            ("25",   160, 1.0),
            ("25",   128, 1.0),
            ("25",   96,  1.0),
            # Phase 4: 22 fps
            ("22",   192, 1.0),
            ("22",   160, 1.0),
            ("22",   128, 1.0),
            ("22",   96,  1.0),
            # Phase 5: 20 fps
            ("20",   192, 1.0),
            ("20",   160, 1.0),
            ("20",   128, 1.0),
            ("20",   96,  1.0),
            ("20",   80,  1.0),
            # Phase 6: 18 fps
            ("18",   160, 1.0),
            ("18",   128, 1.0),
            ("18",   96,  1.0),
            ("18",   80,  1.0),
            # Phase 7: 15 fps
            ("15",   128, 1.0),
            ("15",   96,  1.0),
            ("15",   80,  1.0),
            ("15",   64,  1.0),
            # Phase 8: 12 fps
            ("12",   96,  1.0),
            ("12",   80,  1.0),
            ("12",   64,  1.0),
            ("12",   48,  1.0),
            # Phase 9: 10 fps
            ("10",   80,  1.0),
            ("10",   64,  1.0),
            ("10",   48,  1.0),
            ("10",   32,  1.0),
            # Phase 10: last resort (8-6 fps)
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
            """Run FFmpeg with given fps/colors/scale parameters. Returns (path, size_mb) or (None, 0.0)."""
            filters = []
            if fps != "keep":
                filters.append(f"fps={fps}")
            if scale < 1.0:
                filters.append(f"scale=iw*{scale}:ih*{scale}:flags=lanczos")
            filters.append(
                # stats_mode=diff builds palette from changed pixels only (better for animations)
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
            # ── gifski primary path ────────────────────────────────────────────
            if self.gifski_path and self.gifski_path.exists():
                _orig_fps = 25
                try:
                    with Image.open(gif_path) as _img:
                        _dur = _img.info.get('duration', 40) or 40
                        _orig_fps = max(1, int(round(1000.0 / _dur)))
                except Exception:
                    pass

                gifski_fps_tiers = [None, 24, 20, 15, 12, 10, 8, 6, 4, 3]
                max_bytes = int(max_mb * 1024 * 1024)
                gsk_frames = tmp_dir / "_gsk_frames"

                for fps_cap in gifski_fps_tiers:
                    shutil.rmtree(gsk_frames, ignore_errors=True)
                    gsk_frames.mkdir()
                    cmd_ex = [str(self.ffmpeg_path), "-y", "-i", str(gif_path)]
                    if fps_cap:
                        cmd_ex += ["-vf", f"fps={fps_cap}"]
                    cmd_ex.append(str(gsk_frames / "frame%06d.png"))
                    r_ex = subprocess.run(cmd_ex, capture_output=True,
                                          encoding='utf-8', errors='replace',
                                          timeout=180, **_NO_WINDOW_FLAGS)
                    if r_ex.returncode != 0 or not any(gsk_frames.glob("frame*.png")):
                        log(f"  gifski fps={fps_cap or 'orig'}: extracción falló")
                        continue

                    fps_arg = str(fps_cap) if fps_cap else str(_orig_fps)
                    gsk_out = tmp_dir / "_gsk_out.gif"
                    result = self._gifski_optimal(
                        str(gsk_frames / "frame*.png"), gsk_out, fps_arg, max_bytes
                    )
                    if result is not None:
                        q, size = result
                        size_mb = size / (1024 * 1024)
                        log(f"✅ gifski fps={fps_cap or 'orig'} q={q} → {size_mb:.2f} MB")
                        shutil.copy(gsk_out, out_path)
                        self._write_manifest(out_dir, "optimizar_tamano",
                            {"max_mb": max_mb, "min_mb": min_mb,
                             "engine": "gifski", "fps": fps_cap or "orig", "quality": q,
                             "resultado_mb": round(size_mb, 3),
                             "original_mb": round(original_mb, 3)},
                            archivos=[out_path], fuente=gif_path)
                        self._patch_gif_trailer(out_path)
                        return out_path
                    log(f"  gifski fps={fps_cap or 'orig'}: no cupo bajo {max_mb:.2f} MB")

                log(f"gifski no consiguió bajar de {max_mb:.2f} MB — usando ffmpeg...")

            # ── ffmpeg ladder ──────────────────────────────────────────────────
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
            """Apply one strategy to all input fragments. Returns list of (candidate_path, size_mb)
            if every fragment succeeded, or None if any fragment failed."""
            filters = []
            if fps != "keep":
                filters.append(f"fps={fps}")
            if scale < 1.0:
                filters.append(f"scale=iw*{scale}:ih*{scale}:flags=lanczos")
            filters.append(
                # stats_mode=diff: palette optimised for motion rather than the full colour space
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
            # ── gifski primary path (shared quality across all fragments) ──────
            if self.gifski_path and self.gifski_path.exists():
                _orig_fps = 25
                try:
                    with Image.open(paths[0]) as _img:
                        _dur = _img.info.get('duration', 40) or 40
                        _orig_fps = max(1, int(round(1000.0 / _dur)))
                except Exception:
                    pass

                gifski_fps_tiers = [None, 24, 20, 15, 12, 10, 8, 6, 4, 3]
                max_bytes = int(max_mb * 1024 * 1024)
                gsk_tmp = tmp_dir / "_gsk"
                gsk_tmp.mkdir()

                for fps_cap in gifski_fps_tiers:
                    fps_arg = str(fps_cap) if fps_cap else str(_orig_fps)

                    frame_dirs: List[Path] = []
                    extract_ok = True
                    for i, src in enumerate(paths):
                        fd = gsk_tmp / f"fd_{fps_cap or 0}_{i}"
                        shutil.rmtree(fd, ignore_errors=True)
                        fd.mkdir()
                        cmd_ex = [str(self.ffmpeg_path), "-y", "-i", str(src)]
                        if fps_cap:
                            cmd_ex += ["-vf", f"fps={fps_cap}"]
                        cmd_ex.append(str(fd / "frame%06d.png"))
                        r_ex = subprocess.run(cmd_ex, capture_output=True,
                                              encoding='utf-8', errors='replace',
                                              timeout=180, **_NO_WINDOW_FLAGS)
                        if r_ex.returncode != 0 or not any(fd.glob("frame*.png")):
                            log(f"  gifski batch fps={fps_arg}: extracción falló para {src.name}")
                            extract_ok = False
                            break
                        frame_dirs.append(fd)

                    if not extract_ok:
                        continue

                    # Binary-search shared quality where ALL fragments fit
                    q_lo, q_hi = 10, 95
                    best_q: Optional[int] = None
                    best_gsk_results: Optional[List[Tuple[Path, float]]] = None

                    while q_lo <= q_hi:
                        q = (q_lo + q_hi) // 2
                        frag_results: List[Tuple[Path, float]] = []
                        all_fit = True
                        for i, fd in enumerate(frame_dirs):
                            gsk_out = gsk_tmp / f"q{q}_{i}.gif"
                            r = subprocess.run(
                                [str(self.gifski_path), "--fps", fps_arg,
                                 "--quality", str(q), "--repeat", "0",
                                 "-o", str(gsk_out), str(fd / "frame*.png")],
                                capture_output=True, encoding='utf-8',
                                errors='replace', timeout=180, **_NO_WINDOW_FLAGS,
                            )
                            if r.returncode != 0 or not gsk_out.exists():
                                log(f"   gifski batch q={q} frag {i}: rc={r.returncode}")
                                all_fit = False
                                break
                            size = gsk_out.stat().st_size
                            frag_results.append((gsk_out, size / (1024 * 1024)))
                            if size > max_bytes:
                                all_fit = False
                                break

                        if all_fit and len(frag_results) == len(frame_dirs):
                            best_q = q
                            best_gsk_results = list(frag_results)
                            q_lo = q + 1
                            log(f"   gifski batch fps={fps_arg} q={q} → OK "
                                f"(max={max(r[1] for r in frag_results):.2f} MB)")
                        else:
                            q_hi = q - 1

                    if best_q is not None and best_gsk_results is not None:
                        log(f"✅ gifski batch fps={fps_arg} q={best_q}")
                        all_out_names = [f"{src.stem}_opt.gif" for src in paths]
                        dirs_cleaned_gsk: set = set()
                        _gsk_out_paths: List[Optional[Path]] = []
                        for src in paths:
                            od = self._workspace_dir(src, "optimizado")
                            if od not in dirs_cleaned_gsk:
                                self._archive_before_overwrite(od, keep_names=all_out_names)
                                dirs_cleaned_gsk.add(od)
                        for src, (cand, size_mb) in zip(paths, best_gsk_results):
                            od = self._workspace_dir(src, "optimizado")
                            dst = od / f"{src.stem}_opt.gif"
                            shutil.copy(cand, dst)
                            self._write_manifest(od, "optimizar_tamano_batch",
                                {"max_mb": max_mb, "min_mb": min_mb,
                                 "engine": "gifski", "fps": fps_cap or "orig",
                                 "quality": best_q,
                                 "resultado_mb": round(size_mb, 3),
                                 "estrategia_compartida": True,
                                 "total_fragmentos": len(paths)},
                                archivos=[dst], fuente=src)
                            self._patch_gif_trailer(dst)
                            _gsk_out_paths.append(dst)
                            log(f"✅ {src.name} → {dst.name} ({size_mb:.2f} MB)")
                        return _gsk_out_paths

                    log(f"  gifski batch fps={fps_arg}: ninguna calidad cupo en todos")

                log(f"gifski batch: ningún tier funcionó, usando ffmpeg fallback...")

            # ── ffmpeg ladder ──────────────────────────────────────────────────
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

    def optimize_gif_playback(self, gif_path: Path) -> Optional[Path]:
        """Normalize all GIF frame durations to a single average value (50–200 ms range).
        Eliminates jitter caused by inconsistent per-frame delays."""
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

            avg_duration = max(50, min(200, int(sum(durations) / len(durations))))  # clamp to 50–200 ms

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
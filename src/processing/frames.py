"""processing.frames - frame extraction and AI upscaling (Real-ESRGAN / Real-CUGAN)."""
import subprocess
from pathlib import Path
from typing import Optional, List, Tuple, Callable

from PIL import Image, ImageSequence
from tqdm import tqdm

from processing.common import _NO_WINDOW_FLAGS, logger


class FramesMixin:
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
            try:
                from moviepy import VideoFileClip  # moviepy >= 2.0
            except ImportError:
                from moviepy.editor import VideoFileClip  # moviepy 1.x

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
        
        
    
    


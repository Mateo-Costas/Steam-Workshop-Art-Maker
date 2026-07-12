"""processing.base - SteamProcessorBase: init, workspace helpers, binary/GPU discovery."""
import sys
import shutil
import platform
import subprocess
from pathlib import Path
from typing import Optional, List, Tuple

from config import Config
from models import ModelManager
from analyzers import ContentAnalyzer

from processing.common import _NO_WINDOW_FLAGS, logger


class SteamProcessorBase:
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
    


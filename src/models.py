"""
models.py - AI model registry, download, and selection.

Manages two upscaling engines:
  - Real-ESRGAN (xinntao): general-purpose and anime-optimized models.
  - Real-CUGAN (nihui/Bilibili): anime-specialized models (models-se / models-pro dirs).

On first run the binaries aren't present; ModelManager.download_all_models() fetches
the official GitHub release ZIPs and extracts .exe + .bin/.param files into
SteamWorkshopAppData/. The check_available_models() method scans the disk at
runtime and returns only the IDs whose files are actually present.
"""

import logging
import zipfile
import shutil
import requests
import sys
from pathlib import Path
from typing import List, Dict, Optional, Callable

logger = logging.getLogger("WorkshopArtPRO.models")

class ModelManager:
    """Discovers, downloads, and selects AI upscaling models at runtime."""

    # Static registry of all supported model IDs.
    # 'engine' key distinguishes realesrgan vs realcugan executables.
    # 'files' lists the .bin/.param pair; empty list means the engine uses a model directory instead.
    MODELS_INFO = {
        # === MODELOS ANIME ESPECIALIZADOS ===
        "realesr-animevideov3-x2": {
            "name": "Real-ESRGAN Anime Video v3 (2x)",
            "description": "🎌 Anime/Gaming 2x - Rápido",
            "files": ["realesr-animevideov3-x2.bin", "realesr-animevideov3-x2.param"],
            "best_for": ["anime", "gaming", "videos", "fast_processing"],
            "quality_score": 8,
            "speed_score": 10,
            "size_mb": 1.2,
            "recommended_use": "Escalado rápido 2x para anime/gaming"
        },
        "realesr-animevideov3-x3": {
            "name": "Real-ESRGAN Anime Video v3 (3x)",
            "description": "🎌 Anime/Gaming 3x - Balanceado", 
            "files": ["realesr-animevideov3-x3.bin", "realesr-animevideov3-x3.param"],
            "best_for": ["anime", "gaming", "videos", "balanced"],
            "quality_score": 8,
            "speed_score": 8,
            "size_mb": 1.2,
            "recommended_use": "Escalado balanceado 3x para anime/gaming"
        },
        "realesr-animevideov3-x4": {
            "name": "Real-ESRGAN Anime Video v3 (4x)",
            "description": "🎌 Anime/Gaming 4x - Alta calidad",
            "files": ["realesr-animevideov3-x4.bin", "realesr-animevideov3-x4.param"],
            "best_for": ["anime", "gaming", "videos", "high_quality"],
            "quality_score": 9,
            "speed_score": 7,
            "size_mb": 1.2,
            "recommended_use": "Máxima calidad 4x para anime/gaming - RECOMENDADO"
        },
        "realesrgan-x4plus-anime": {
            "name": "Real-ESRGAN x4plus Anime 6B",
            "description": "🎨 Anime especializado - Premium",
            "files": ["realesrgan-x4plus-anime.bin", "realesrgan-x4plus-anime.param"],
            "best_for": ["anime", "illustrations", "artwork", "premium_quality"],
            "quality_score": 10,
            "speed_score": 5,
            "size_mb": 8.5,
            "recommended_use": "Máxima calidad para ilustraciones anime"
        },
        
        # === MODELOS DE USO GENERAL ===
        "realesrgan-x4plus": {
            "name": "Real-ESRGAN x4plus Universal",
            "description": "🖼️ Uso general - Versátil",
            "files": ["realesrgan-x4plus.bin", "realesrgan-x4plus.param"],
            "best_for": ["general", "mixed", "versatile", "all_content"],
            "quality_score": 8,
            "speed_score": 6,
            "size_mb": 32,
            "recommended_use": "Modelo versátil para todo tipo de contenido"
        },
        "realesrnet-x4plus": {
            "name": "Real-ESRNet x4plus",
            "description": "📷 Fotos realistas",
            "files": ["realesrnet-x4plus.bin", "realesrnet-x4plus.param"],
            "best_for": ["photos", "realistic", "portraits", "natural"],
            "quality_score": 7,
            "speed_score": 9,
            "size_mb": 64,
            "recommended_use": "Optimizado para fotografías y contenido realista"
        },
        
        # === MODELOS LIGEROS Y RÁPIDOS ===
        "realesr-general-x4v3": {
            "name": "Real-ESRGAN General v3",
            "description": "⚡ Ligero y rápido",
            "files": ["realesr-general-x4v3.bin", "realesr-general-x4v3.param"],
            "best_for": ["fast", "general", "lightweight", "quick_processing"],
            "quality_score": 7,
            "speed_score": 10,
            "size_mb": 4,
            "recommended_use": "Procesamiento rápido con calidad decente"
        },
        "realesr-general-wdn-x4v3": {
            "name": "Real-ESRGAN General WDN v3",
            "description": "⚡ Ligero con denoise",
            "files": ["realesr-general-wdn-x4v3.bin", "realesr-general-wdn-x4v3.param"],
            "best_for": ["fast", "general", "denoise", "noisy_images"],
            "quality_score": 7,
            "speed_score": 9,
            "size_mb": 4,
            "recommended_use": "Procesamiento rápido con reducción de ruido"
        },
        
        # === MODELOS EXPERIMENTALES (si existen) ===
        "RealESRGAN_x2plus": {
            "name": "Real-ESRGAN x2plus",
            "description": "Escalado 2x rapido",
            "files": ["RealESRGAN_x2plus.bin", "RealESRGAN_x2plus.param"],
            "best_for": ["fast", "2x_scaling", "quick_preview"],
            "quality_score": 7,
            "speed_score": 10,
            "size_mb": 64,
            "recommended_use": "Escalado rapido 2x para previsualizaciones"
        },

        # === REAL-CUGAN (Bilibili) - Anime especializado ===
        "cugan-se-2x-no-denoise": {
            "name": "Real-CUGAN SE 2x",
            "description": "CUGAN Anime 2x - Sin denoise",
            "engine": "realcugan",
            "cugan_args": {"scale": 2, "noise": 0, "model_dir": "models-se"},
            "files": [],  # Se gestionan por directorio
            "best_for": ["anime", "illustrations", "clean_source"],
            "quality_score": 9,
            "speed_score": 9,
            "size_mb": 5,
            "recommended_use": "Anime limpio 2x - lineas nítidas"
        },
        "cugan-se-2x-denoise3": {
            "name": "Real-CUGAN SE 2x Denoise",
            "description": "CUGAN Anime 2x - Denoise fuerte",
            "engine": "realcugan",
            "cugan_args": {"scale": 2, "noise": 3, "model_dir": "models-se"},
            "files": [],
            "best_for": ["anime", "noisy_anime", "old_anime"],
            "quality_score": 9,
            "speed_score": 8,
            "size_mb": 5,
            "recommended_use": "Anime con ruido 2x - limpieza + upscale"
        },
        "cugan-se-3x-no-denoise": {
            "name": "Real-CUGAN SE 3x",
            "description": "CUGAN Anime 3x - Sin denoise",
            "engine": "realcugan",
            "cugan_args": {"scale": 3, "noise": 0, "model_dir": "models-se"},
            "files": [],
            "best_for": ["anime", "illustrations", "high_quality"],
            "quality_score": 9,
            "speed_score": 7,
            "size_mb": 5,
            "recommended_use": "Anime 3x - calidad alta"
        },
        "cugan-se-4x-no-denoise": {
            "name": "Real-CUGAN SE 4x",
            "description": "CUGAN Anime 4x - Maxima calidad",
            "engine": "realcugan",
            "cugan_args": {"scale": 4, "noise": 0, "model_dir": "models-se"},
            "files": [],
            "best_for": ["anime", "illustrations", "premium_quality"],
            "quality_score": 10,
            "speed_score": 5,
            "size_mb": 5,
            "recommended_use": "Anime 4x - maxima calidad (solo models-se)"
        },
        "cugan-pro-2x-denoise3": {
            "name": "Real-CUGAN Pro 2x Denoise",
            "description": "CUGAN Pro Anime 2x - Premium",
            "engine": "realcugan",
            "cugan_args": {"scale": 2, "noise": 3, "model_dir": "models-pro"},
            "files": [],
            "best_for": ["anime", "premium_quality", "noisy_anime"],
            "quality_score": 10,
            "speed_score": 7,
            "size_mb": 5,
            "recommended_use": "Anime premium 2x con denoise"
        },
        "cugan-pro-3x-no-denoise": {
            "name": "Real-CUGAN Pro 3x",
            "description": "CUGAN Pro Anime 3x - Premium",
            "engine": "realcugan",
            "cugan_args": {"scale": 3, "noise": 0, "model_dir": "models-pro"},
            "files": [],
            "best_for": ["anime", "illustrations", "premium_quality"],
            "quality_score": 10,
            "speed_score": 6,
            "size_mb": 5,
            "recommended_use": "Anime premium 3x"
        },
    }
    
    # GitHub release URLs for the two engine ZIPs.
    # Each ZIP contains both the executable and the model files.
    DOWNLOAD_PACKAGES = [
        {
            "name": "Real-ESRGAN ncnn Vulkan Windows",
            "url": "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesrgan-ncnn-vulkan-20220424-windows.zip",
            "contains": ["executable", "all_models"],
            "engine": "realesrgan",
            "required": True
        },
        {
            "name": "Real-CUGAN ncnn Vulkan Windows",
            "url": "https://github.com/nihui/realcugan-ncnn-vulkan/releases/download/20220728/realcugan-ncnn-vulkan-20220728-windows.zip",
            "contains": ["executable", "cugan_models"],
            "engine": "realcugan",
            "required": False
        }
    ]
    
    def __init__(self, models_dir: Path):
        # When frozen (PyInstaller .exe), resolve paths relative to the executable,
        # not the current working directory of the process.
        if getattr(sys, 'frozen', False):
            self.project_dir = Path(sys.executable).parent
            base_path = Path(sys.executable).parent
            self.models_dir = base_path / "SteamWorkshopAppData" / "models"
        else:
            self.project_dir = Path.cwd()
            self.models_dir = Path(models_dir)
        
        self.models_dir.mkdir(parents=True, exist_ok=True)
        
        # Buscar ejecutables
        self.exe_path = self._find_realesrgan_exe()
        self.cugan_exe_path = self._find_cugan_exe()
        
    def _find_realesrgan_exe(self) -> Optional[Path]:
        """Return the path to realesrgan-ncnn-vulkan.exe, or None if not found.
        Checks SteamWorkshopAppData/ first (preferred), then the exe root (legacy)."""
        if getattr(sys, 'frozen', False):
            base_path = Path(sys.executable).parent
        else:
            base_path = Path.cwd()

        locations = [
            base_path / "SteamWorkshopAppData" / "realesrgan-ncnn-vulkan.exe",  # nueva ubicación
            base_path / "realesrgan-ncnn-vulkan.exe",                            # legacy
            base_path / "_internal" / "realesrgan-ncnn-vulkan.exe",
            Path.cwd() / "realesrgan-ncnn-vulkan.exe",
        ]

        for loc in locations:
            if loc.exists():
                return loc

        return None

    def _find_cugan_exe(self) -> Optional[Path]:
        """Return the path to realcugan-ncnn-vulkan.exe, or None if not found."""
        if getattr(sys, 'frozen', False):
            base_path = Path(sys.executable).parent
        else:
            base_path = Path.cwd()

        locations = [
            base_path / "SteamWorkshopAppData" / "realcugan-ncnn-vulkan.exe",  # nueva ubicación
            base_path / "realcugan-ncnn-vulkan.exe",                            # legacy
            base_path / "_internal" / "realcugan-ncnn-vulkan.exe",
            Path.cwd() / "realcugan-ncnn-vulkan.exe",
        ]

        for loc in locations:
            if loc.exists():
                return loc

        return None

    def check_cugan_executable(self) -> bool:
        """Verificar si el ejecutable de Real-CUGAN existe"""
        return self.cugan_exe_path is not None and self.cugan_exe_path.exists()

    def check_available_models(self) -> List[str]:
        """Scan disk and return IDs of models whose files are actually present.

        CUGAN models are considered available only when both the executable and
        the corresponding model directory (models-se or models-pro) exist.
        Also discovers any ESRGAN .bin/.param pairs not in MODELS_INFO.
        """
        available = []

        for model_id, info in self.MODELS_INFO.items():
            engine = info.get("engine", "realesrgan")

            if engine == "realcugan":
                # CUGAN needs the exe AND its model subdirectory (models-se/models-pro)
                if self.check_cugan_executable():
                    cugan_args = info.get("cugan_args", {})
                    model_dir_name = cugan_args.get("model_dir", "models-se")
                    if self.cugan_exe_path:
                        model_dir = self.cugan_exe_path.parent / model_dir_name
                        if model_dir.exists():
                            available.append(model_id)
            else:
                # ESRGAN: verify both .bin and .param are present
                if self._check_model_files(model_id):
                    available.append(model_id)

        # Discover any user-added ESRGAN models not in the registry
        for bin_file in self.models_dir.glob("*.bin"):
            param_file = bin_file.with_suffix('.param')
            if param_file.exists() and bin_file.stem not in self.MODELS_INFO:
                available.append(bin_file.stem)

        return available
    
    def _check_model_files(self, model_id: str) -> bool:
        """Verificar si los archivos del modelo existen"""
        bin_file = self.models_dir / f"{model_id}.bin"
        param_file = self.models_dir / f"{model_id}.param"
        return bin_file.exists() and param_file.exists()
    
    def check_executable(self) -> bool:
        """Verificar si el ejecutable de Real-ESRGAN existe"""
        return (
            (self.project_dir / "SteamWorkshopAppData" / "realesrgan-ncnn-vulkan.exe").exists()
            or (self.project_dir / "realesrgan-ncnn-vulkan.exe").exists()
        )
    
    def download_all_models(self, progress_callback: Optional[Callable] = None) -> bool:
        """Download Real-ESRGAN and (optionally) Real-CUGAN from GitHub releases.
        Skips download if 3+ models and the executable are already present.
        progress_callback(message: str, percent: float) is called throughout."""
        try:
            if progress_callback:
                progress_callback("Iniciando descarga...", 0)
            
            # Verificar si ya tenemos suficientes modelos
            available_models = self.check_available_models()
            exe_exists = self.check_executable()
            
            if len(available_models) >= 3 and exe_exists:
                if progress_callback:
                    progress_callback("Ya tienes modelos suficientes", 100)
                logger.info("Modelos suficientes ya disponibles")
                return True
            
            # Crear directorio temporal
            temp_dir = Path("SteamWorkshopAppData/temp")
            temp_dir.mkdir(parents=True, exist_ok=True)
            
            # Descargar paquete principal (Real-ESRGAN)
            package = self.DOWNLOAD_PACKAGES[0]

            if progress_callback:
                progress_callback(f"Descargando {package['name']}...", 10)

            success = self._download_and_extract_complete_package(package, temp_dir, progress_callback)

            # Descargar Real-CUGAN (opcional)
            if len(self.DOWNLOAD_PACKAGES) > 1:
                cugan_package = self.DOWNLOAD_PACKAGES[1]
                if progress_callback:
                    progress_callback(f"Descargando {cugan_package['name']}...", 70)
                cugan_ok = self._download_and_extract_complete_package(cugan_package, temp_dir, progress_callback)
                if cugan_ok:
                    self.cugan_exe_path = self._find_cugan_exe()
                    logger.info("Real-CUGAN descargado correctamente")
                else:
                    logger.warning("Real-CUGAN no se pudo descargar (opcional)")

            if success:
                # Verificar instalación
                if progress_callback:
                    progress_callback("Verificando instalación...", 90)
                
                available_models = self.check_available_models()
                exe_exists = self.check_executable()
                
                if progress_callback:
                    progress_callback(f"Completado: {len(available_models)} modelos + ejecutable", 100)
                
                # Limpiar directorio temporal
                try:
                    shutil.rmtree(temp_dir)
                except Exception:
                    pass
                
                # Consideramos éxito si tenemos ejecutable Y al menos 2 modelos
                result = exe_exists and len(available_models) >= 2
                
                if result:
                    logger.info("Descarga exitosa: %d modelos disponibles", len(available_models))
                else:
                    logger.warning("Descarga parcial: exe=%s modelos=%d", exe_exists, len(available_models))
                
                return result
            else:
                if progress_callback:
                    progress_callback("Error en la descarga", 0)
                return False
            
        except Exception as e:
            logger.error("Error general descargando: %s", e)
            if progress_callback:
                progress_callback(f"Error: {e}", 0)
            return False
    
    def _download_and_extract_complete_package(self, package: dict, temp_dir: Path,
                                              progress_callback: Optional[Callable]) -> bool:
        """Download a single engine ZIP and extract .exe + .bin/.param files from it.
        Does a HEAD request first to verify the URL is reachable before streaming."""
        try:
            zip_path = temp_dir / "realesrgan-complete.zip"
            
            if progress_callback:
                progress_callback("Conectando al servidor...", 15)
            
            # Verificar que la URL es accesible primero
            logger.debug("Verificando URL: %s", package['url'])
            
            # Hacer una petición HEAD primero para verificar
            head_response = requests.head(package['url'], timeout=30)
            if head_response.status_code != 200:
                logger.warning("URL no accesible: codigo %d", head_response.status_code)
                return False
            
            # Descargar archivo con timeout más largo
            logger.info("Iniciando descarga desde GitHub...")
            response = requests.get(package['url'], stream=True, timeout=60)
            response.raise_for_status()
            
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            
            if progress_callback:
                progress_callback(f"Descargando... 0/{total_size/(1024*1024):.1f} MB", 20)
            
            logger.info("Tamaño total: %.1f MB", total_size / (1024 * 1024))
            
            with open(zip_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        
                        if progress_callback and total_size > 0:
                            progress = 20 + ((downloaded / total_size) * 50)
                            progress_callback(
                                f"Descargando... {downloaded/(1024*1024):.1f}/{total_size/(1024*1024):.1f} MB", 
                                progress
                            )
            
            logger.info("Descarga completada: %s", zip_path)
            
            if progress_callback:
                progress_callback("Extrayendo archivos...", 75)
            
            # Extraer todo el contenido
            extracted_models = 0
            extracted_exe = False
            
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                all_files = zip_ref.namelist()
                total_files = len([f for f in all_files if not f.endswith('/')])
                
                logger.debug("Archivos en ZIP: %d", total_files)
                
                for idx, member in enumerate(all_files):
                    if member.endswith('/'):
                        continue
                    
                    filename = Path(member).name
                    
                    # Determinar destino según tipo de archivo
                    if filename.endswith('.exe'):
                        dest = self.project_dir / "SteamWorkshopAppData" / filename
                        if progress_callback:
                            progress_callback(f"Extrayendo ejecutable: {filename}", 75 + (idx/total_files)*10)
                        logger.debug("Extrayendo ejecutable: %s", filename)
                        extracted_exe = True
                    elif filename.endswith(('.bin', '.param')):
                        dest = self.models_dir / filename
                        if progress_callback:
                            progress_callback(f"Extrayendo modelo: {filename}", 75 + (idx/total_files)*10)
                        logger.debug("Extrayendo modelo: %s", filename)
                        if filename.endswith('.bin'):
                            extracted_models += 1
                    else:
                        # Ignorar otros archivos (documentación, etc.)
                        continue
                    
                    # Crear directorio si no existe
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    
                    # Extraer archivo
                    with zip_ref.open(member) as source, open(dest, 'wb') as target:
                        target.write(source.read())
                    
                    logger.debug("Extraido: %s", dest)
            
            # Limpiar zip
            zip_path.unlink()
            
            if progress_callback:
                progress_callback("Verificando archivos extraídos...", 85)
            
            logger.info("Extraccion: exe=%s modelos=%d archivos .bin", extracted_exe, extracted_models)
            
            # Verificar que se extrajeron correctamente
            exe_exists = self.check_executable()
            available_models = self.check_available_models()
            
            success = exe_exists and len(available_models) > 0
            
            if success:
                logger.info("Extraccion exitosa: %d modelos disponibles", len(available_models))
            else:
                logger.warning("Extraccion incompleta: exe=%s modelos=%d", exe_exists, len(available_models))
            
            return success
            
        except requests.exceptions.RequestException as e:
            logger.error("Error de red descargando: %s", e)
            if "404" in str(e):
                logger.warning("La URL puede haber cambiado. Verifica releases de GitHub.")
            return False
        except Exception as e:
            logger.error("Error descargando paquete completo: %s", e)
            return False
    
    def get_model_recommendation(self, content_analysis: Dict) -> str:
        """Map a ContentAnalyzer result to the best available model ID.
        Falls back to the first available model if the preferred one isn't installed."""
        content_type = content_analysis.get("type", "unknown")
        
        # Mapeo con modelos reales (CUGAN preferido para anime puro)
        model_mapping = {
            "anime/gaming": "cugan-se-4x-no-denoise",
            "anime/illustration": "cugan-se-4x-no-denoise",
            "gaming/mixed": "realesrgan-x4plus",
            "realistic/photo": "realesrgan-x4plus",
            "dark/gaming": "realesr-animevideov3-x4",
            "mixed": "realesrgan-x4plus"
        }
        
        recommended = model_mapping.get(content_type, "realesrgan-x4plus")
        
        # Verificar si el modelo recomendado está disponible
        available = self.check_available_models()
        
        if recommended not in available:
            logger.warning("Modelo recomendado '%s' no disponible", recommended)
            
            # Buscar alternativa disponible
            if available:
                # Prioridades de fallback
                if "anime" in content_type:
                    # Para anime, preferir modelos anime
                    anime_models = [m for m in available if "anime" in m]
                    if anime_models:
                        recommended = anime_models[0]
                        logger.info("Usando modelo anime alternativo: %s", recommended)
                    else:
                        recommended = available[0]
                        logger.info("Usando primer modelo disponible: %s", recommended)
                else:
                    recommended = available[0]
                    logger.info("Usando primer modelo disponible: %s", recommended)
            else:
                logger.error("No hay modelos disponibles")
                return "realesrgan-x4plus"  # Fallback por defecto
        
        return recommended
    
    def get_model_info(self, model_id: str) -> Dict:
        """Obtener información detallada de un modelo"""
        if model_id in self.MODELS_INFO:
            return self.MODELS_INFO[model_id]
        else:
            # Para modelos no listados, crear info básica
            return {
                "name": model_id,
                "description": f"📂 Modelo: {model_id}",
                "files": [f"{model_id}.bin", f"{model_id}.param"],
                "best_for": ["unknown"],
                "quality_score": 7,
                "speed_score": 7,
                "size_mb": 0
            }
    
    def get_all_models_info(self) -> Dict[str, Dict]:
        """Obtener información de todos los modelos"""
        return self.MODELS_INFO.copy()
    
    def verify_installation(self) -> Dict[str, bool]:
        """Verificar instalación completa"""
        results = {
            "executable": self.check_executable(),
            "models": {}
        }
        
        available_models = self.check_available_models()
        
        for model_id in self.MODELS_INFO:
            results["models"][model_id] = model_id in available_models
        
        # Agregar modelos no listados
        for model_id in available_models:
            if model_id not in self.MODELS_INFO:
                results["models"][model_id] = True
        
        results["total_models"] = len(available_models)
        results["complete"] = results["executable"] and results["total_models"] >= 2
        
        return results
    
    def get_recommended_for_user(self) -> str:
        """Obtener modelo recomendado para gaming/anime (usuario específico)"""
        available = self.check_available_models()
        
        # Prioridades para gaming/anime
        priorities = [
            "realesr-animevideov3-x4",      # Mejor para anime/gaming 4x
            "realesrgan-x4plus-anime",       # Anime alta calidad
            "realesr-animevideov3-x3",      # Anime 3x
            "realesr-animevideov3-x2",      # Anime 2x (más rápido)
            "realesrgan-x4plus"             # General
        ]
        
        for model in priorities:
            if model in available:
                return model
        
        # Fallback
        return available[0] if available else "realesrgan-x4plus"
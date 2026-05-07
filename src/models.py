"""
models.py - Gestión de modelos de IA (descarga, verificación y selección)
"""

import queue
import zipfile
import shutil
import requests
import sys
from pathlib import Path
from typing import List, Dict, Optional, Callable

class ModelManager:
    """Gestión de descarga, verificación y selección de modelos de IA."""

    # Modelos verificados y sus archivos asociados
    # LISTA COMPLETA Y ACTUALIZADA de modelos Real-ESRGAN
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
    
    # URLs VERIFICADAS que funcionan
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
        # Si estamos en un ejecutable, buscar models en el directorio del exe
        if getattr(sys, 'frozen', False):
            self.project_dir = Path(sys.executable).parent
            base_path = Path(sys.executable).parent
            self.models_dir = base_path / "models"
        else:
            self.project_dir = Path.cwd()
            self.models_dir = Path(models_dir)
        
        self.models_dir.mkdir(parents=True, exist_ok=True)
        
        # Buscar ejecutables
        self.exe_path = self._find_realesrgan_exe()
        self.cugan_exe_path = self._find_cugan_exe()
        
    def _find_realesrgan_exe(self) -> Optional[Path]:
        """Buscar ejecutable Real-ESRGAN"""
        if getattr(sys, 'frozen', False):
            base_path = Path(sys.executable).parent
        else:
            base_path = Path.cwd()
        
        # Buscar en varias ubicaciones
        locations = [
            base_path / "realesrgan-ncnn-vulkan.exe",
            base_path / "_internal" / "realesrgan-ncnn-vulkan.exe",
            Path.cwd() / "realesrgan-ncnn-vulkan.exe",
        ]
        
        for loc in locations:
            if loc.exists():
                return loc
        
        return None

    def _find_cugan_exe(self) -> Optional[Path]:
        """Buscar ejecutable Real-CUGAN"""
        if getattr(sys, 'frozen', False):
            base_path = Path(sys.executable).parent
        else:
            base_path = Path.cwd()

        locations = [
            base_path / "realcugan-ncnn-vulkan.exe",
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
        """Verificar modelos disponibles (Real-ESRGAN + Real-CUGAN)"""
        available = []

        for model_id, info in self.MODELS_INFO.items():
            engine = info.get("engine", "realesrgan")

            if engine == "realcugan":
                # CUGAN: necesita el exe + el directorio de modelos
                if self.check_cugan_executable():
                    cugan_args = info.get("cugan_args", {})
                    model_dir_name = cugan_args.get("model_dir", "models-se")
                    # Buscar directorio de modelos junto al exe
                    if self.cugan_exe_path:
                        model_dir = self.cugan_exe_path.parent / model_dir_name
                        if model_dir.exists():
                            available.append(model_id)
            else:
                # Real-ESRGAN: buscar .bin + .param
                if self._check_model_files(model_id):
                    available.append(model_id)

        # También buscar modelos ESRGAN no listados
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
        exe_path = self.project_dir / "realesrgan-ncnn-vulkan.exe"
        return exe_path.exists()
    
    def download_all_models(self, progress_callback: Optional[Callable] = None) -> bool:
        """Descargar paquete completo CORREGIDO"""
        try:
            if progress_callback:
                progress_callback("Iniciando descarga...", 0)
            
            # Verificar si ya tenemos suficientes modelos
            available_models = self.check_available_models()
            exe_exists = self.check_executable()
            
            if len(available_models) >= 3 and exe_exists:
                if progress_callback:
                    progress_callback("Ya tienes modelos suficientes", 100)
                print("✅ Ya tienes modelos suficientes")
                return True
            
            # Crear directorio temporal
            temp_dir = Path("temp_download")
            temp_dir.mkdir(exist_ok=True)
            
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
                    print("Real-CUGAN descargado correctamente")
                else:
                    print("Real-CUGAN no se pudo descargar (opcional)")

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
                    print(f"✅ Descarga exitosa: {len(available_models)} modelos disponibles")
                else:
                    print(f"⚠️ Descarga parcial: exe={exe_exists}, modelos={len(available_models)}")
                
                return result
            else:
                if progress_callback:
                    progress_callback("Error en la descarga", 0)
                return False
            
        except Exception as e:
            print(f"Error general descargando: {e}")
            if progress_callback:
                progress_callback(f"Error: {e}", 0)
            return False
    
    def _download_and_extract_complete_package(self, package: dict, temp_dir: Path, 
                                             progress_callback: Optional[Callable]) -> bool:
        """Descargar y extraer el paquete completo CORREGIDO"""
        try:
            zip_path = temp_dir / "realesrgan-complete.zip"
            
            if progress_callback:
                progress_callback("Conectando al servidor...", 15)
            
            # Verificar que la URL es accesible primero
            print(f"🔍 Verificando URL: {package['url']}")
            
            # Hacer una petición HEAD primero para verificar
            head_response = requests.head(package['url'], timeout=30)
            if head_response.status_code != 200:
                print(f"❌ URL no accesible: código {head_response.status_code}")
                return False
            
            # Descargar archivo con timeout más largo
            print(f"📥 Iniciando descarga desde GitHub...")
            response = requests.get(package['url'], stream=True, timeout=60)
            response.raise_for_status()
            
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            
            if progress_callback:
                progress_callback(f"Descargando... 0/{total_size/(1024*1024):.1f} MB", 20)
            
            print(f"📊 Tamaño total: {total_size/(1024*1024):.1f} MB")
            
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
            
            print(f"✅ Descarga completada: {zip_path}")
            
            if progress_callback:
                progress_callback("Extrayendo archivos...", 75)
            
            # Extraer todo el contenido
            extracted_models = 0
            extracted_exe = False
            
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                all_files = zip_ref.namelist()
                total_files = len([f for f in all_files if not f.endswith('/')])
                
                print(f"📂 Archivos en ZIP: {total_files}")
                
                for idx, member in enumerate(all_files):
                    if member.endswith('/'):
                        continue
                    
                    filename = Path(member).name
                    
                    # Determinar destino según tipo de archivo
                    if filename.endswith('.exe'):
                        dest = self.project_dir / filename
                        if progress_callback:
                            progress_callback(f"Extrayendo ejecutable: {filename}", 75 + (idx/total_files)*10)
                        print(f"📦 Extrayendo ejecutable: {filename}")
                        extracted_exe = True
                    elif filename.endswith(('.bin', '.param')):
                        dest = self.models_dir / filename
                        if progress_callback:
                            progress_callback(f"Extrayendo modelo: {filename}", 75 + (idx/total_files)*10)
                        print(f"📦 Extrayendo modelo: {filename}")
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
                    
                    print(f"✅ Extraído: {dest}")
            
            # Limpiar zip
            zip_path.unlink()
            
            if progress_callback:
                progress_callback("Verificando archivos extraídos...", 85)
            
            print(f"📊 Resumen extracción:")
            print(f"   Ejecutable: {'✅' if extracted_exe else '❌'}")
            print(f"   Modelos: {extracted_models} archivos .bin")
            
            # Verificar que se extrajeron correctamente
            exe_exists = self.check_executable()
            available_models = self.check_available_models()
            
            success = exe_exists and len(available_models) > 0
            
            if success:
                print(f"✅ Extracción exitosa: {len(available_models)} modelos disponibles")
            else:
                print(f"❌ Extracción incompleta: exe={exe_exists}, modelos={len(available_models)}")
            
            return success
            
        except requests.exceptions.RequestException as e:
            print(f"❌ Error de red descargando: {e}")
            if "404" in str(e):
                print("💡 La URL puede haber cambiado. Verifica releases de GitHub.")
            return False
        except Exception as e:
            print(f"❌ Error descargando paquete completo: {e}")
            return False
    
    def get_model_recommendation(self, content_analysis: Dict) -> str:
        """Obtener recomendación de modelo basada en análisis"""
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
            print(f"⚠️ Modelo recomendado '{recommended}' no disponible")
            
            # Buscar alternativa disponible
            if available:
                # Prioridades de fallback
                if "anime" in content_type:
                    # Para anime, preferir modelos anime
                    anime_models = [m for m in available if "anime" in m]
                    if anime_models:
                        recommended = anime_models[0]
                        print(f"🔄 Usando modelo anime alternativo: {recommended}")
                    else:
                        recommended = available[0]
                        print(f"🔄 Usando primer modelo disponible: {recommended}")
                else:
                    recommended = available[0]
                    print(f"🔄 Usando primer modelo disponible: {recommended}")
            else:
                print("❌ No hay modelos disponibles")
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
"""
models.py - AI model registry, discovery and download.

Two upscaling engines are supported:
  - Real-ESRGAN (xinntao): general-purpose and anime models, one .bin/.param
    pair per model in the models folder.
  - Real-CUGAN (nihui/Bilibili): anime SE models, in models-se/ next to the
    executable. The Pro family of the ncnn port returns black or corrupted
    frames on some content (pure black, saturated colors), so it is not offered.

download_all_models() fetches the official release ZIPs into
SteamWorkshopAppData/; check_available_models() reports only the models whose
files are actually on disk.
"""

import logging
import re
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Callable, Dict, List, Optional

from app_paths import APP_DIR, DATA_DIR, find_tool
from downloads import download_file

logger = logging.getLogger("WorkshopArt.models")

ESRGAN_URL = ("https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/"
              "realesrgan-ncnn-vulkan-20220424-windows.zip")
CUGAN_URL = ("https://github.com/nihui/realcugan-ncnn-vulkan/releases/download/20220728/"
             "realcugan-ncnn-vulkan-20220728-windows.zip")

#: File names of Real-CUGAN networks; an old version of the downloader dumped
#: them into the ESRGAN models folder, where they must not be listed.
_CUGAN_FILE_RE = re.compile(r"^up\dx-")


class ModelManager:
    """Discovers, downloads, and describes the AI upscaling models."""

    # 'engine' distinguishes the executables; 'scale' is the model's native
    # upscale factor (Real-ESRGAN must be called with exactly that -s value).
    MODELS_INFO = {
        # === Anime ===
        "realesr-animevideov3-x2": {
            "name": "Real-ESRGAN Anime Video v3 (2x)",
            "description": "Anime/Gaming 2x - Rapido",
            "scale": 2,
            "quality_score": 8, "speed_score": 10,
        },
        "realesr-animevideov3-x3": {
            "name": "Real-ESRGAN Anime Video v3 (3x)",
            "description": "Anime/Gaming 3x - Equilibrado",
            "scale": 3,
            "quality_score": 8, "speed_score": 8,
        },
        "realesr-animevideov3-x4": {
            "name": "Real-ESRGAN Anime Video v3 (4x)",
            "description": "Anime/Gaming 4x - Alta calidad",
            "scale": 4,
            "quality_score": 9, "speed_score": 7,
        },
        "realesrgan-x4plus-anime": {
            "name": "Real-ESRGAN x4plus Anime 6B",
            "description": "Ilustracion anime - Maxima calidad",
            "scale": 4,
            "quality_score": 10, "speed_score": 5,
        },
        # === General purpose ===
        "realesrgan-x4plus": {
            "name": "Real-ESRGAN x4plus",
            "description": "Uso general - Versatil",
            "scale": 4,
            "quality_score": 8, "speed_score": 6,
        },
        # Not in the official download; recognised if the user adds them.
        "realesrnet-x4plus": {
            "name": "Real-ESRNet x4plus",
            "description": "Fotos realistas",
            "scale": 4,
            "quality_score": 7, "speed_score": 9,
        },
        "realesr-general-x4v3": {
            "name": "Real-ESRGAN General v3",
            "description": "Ligero y rapido",
            "scale": 4,
            "quality_score": 7, "speed_score": 10,
        },
        # === Real-CUGAN (anime) ===
        "cugan-se-2x-no-denoise": {
            "name": "Real-CUGAN SE 2x", "description": "CUGAN anime 2x - Sin denoise",
            "engine": "realcugan", "cugan_args": {"scale": 2, "noise": 0, "model_dir": "models-se"},
            "quality_score": 9, "speed_score": 9,
        },
        "cugan-se-2x-denoise3": {
            "name": "Real-CUGAN SE 2x Denoise", "description": "CUGAN anime 2x - Denoise fuerte",
            "engine": "realcugan", "cugan_args": {"scale": 2, "noise": 3, "model_dir": "models-se"},
            "quality_score": 9, "speed_score": 8,
        },
        "cugan-se-3x-no-denoise": {
            "name": "Real-CUGAN SE 3x", "description": "CUGAN anime 3x - Sin denoise",
            "engine": "realcugan", "cugan_args": {"scale": 3, "noise": 0, "model_dir": "models-se"},
            "quality_score": 9, "speed_score": 7,
        },
        "cugan-se-4x-no-denoise": {
            "name": "Real-CUGAN SE 4x", "description": "CUGAN anime 4x - Maxima calidad",
            "engine": "realcugan", "cugan_args": {"scale": 4, "noise": 0, "model_dir": "models-se"},
            "quality_score": 10, "speed_score": 5,
        },
    }

    def __init__(self, models_dir: Path):
        self.models_dir = Path(models_dir)
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self.exe_path = find_tool("realesrgan-ncnn-vulkan")
        self.cugan_exe_path = find_tool("realcugan-ncnn-vulkan")

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------
    def cugan_models_dir(self, family: str) -> Path:
        """Folder of a Real-CUGAN model family (models-se...)."""
        candidates = [DATA_DIR / family, APP_DIR / family]
        if self.cugan_exe_path:
            candidates.insert(1, self.cugan_exe_path.parent / family)
        return next((c for c in candidates if c.is_dir()), candidates[0])

    def model_scale(self, model_id: str) -> int:
        """Native upscale factor of a Real-ESRGAN model (from the registry or its name)."""
        scale = self.MODELS_INFO.get(model_id, {}).get("scale")
        if scale:
            return int(scale)
        match = re.search(r"x(\d)(?:plus|v\d)?$|-x(\d)", model_id)
        return int(next(g for g in match.groups() if g)) if match else 4

    def check_available_models(self) -> List[str]:
        """IDs of the models whose files are on disk (registry order, then user-added)."""
        available = []
        for model_id, info in self.MODELS_INFO.items():
            if info.get("engine") == "realcugan":
                family = info["cugan_args"]["model_dir"]
                if self.cugan_exe_path and self.cugan_models_dir(family).is_dir():
                    available.append(model_id)
            elif self._has_model_files(model_id):
                available.append(model_id)
        for bin_file in sorted(self.models_dir.glob("*.bin")):
            model_id = bin_file.stem
            if (model_id not in self.MODELS_INFO and not _CUGAN_FILE_RE.match(model_id)
                    and bin_file.with_suffix(".param").exists()):
                available.append(model_id)
        return available

    def _has_model_files(self, model_id: str) -> bool:
        return ((self.models_dir / f"{model_id}.bin").exists()
                and (self.models_dir / f"{model_id}.param").exists())

    def check_executable(self) -> bool:
        """True when the Real-ESRGAN executable is available."""
        return self.exe_path is not None and self.exe_path.exists()

    def get_model_info(self, model_id: str) -> Dict:
        """Registry entry of a model (a generic one for user-added models)."""
        if model_id in self.MODELS_INFO:
            return self.MODELS_INFO[model_id]
        return {"name": model_id, "description": f"Modelo: {model_id}",
                "scale": self.model_scale(model_id),
                "quality_score": 7, "speed_score": 7}

    # ------------------------------------------------------------------
    # Download
    # ------------------------------------------------------------------
    def download_all_models(self, progress_callback: Optional[Callable] = None) -> bool:
        """Download Real-ESRGAN (required) and Real-CUGAN (optional).

        progress_callback(message: str, percent: float). Returns True when the
        Real-ESRGAN executable and at least one model are available.
        """
        def report(message, percent):
            logger.info(message)
            if progress_callback:
                progress_callback(message, percent)

        work = Path(tempfile.mkdtemp(prefix="wkart_models_"))
        try:
            if not (self.check_executable() and self._has_model_files("realesrgan-x4plus")):
                zip_path = download_file(
                    ESRGAN_URL, work / "esrgan.zip", "Real-ESRGAN",
                    lambda m, p: report(m, 5 + p * 0.45))
                report("Extrayendo Real-ESRGAN...", 50)
                self._extract_esrgan(zip_path)
            if not self.cugan_exe_path:
                try:
                    zip_path = download_file(
                        CUGAN_URL, work / "cugan.zip", "Real-CUGAN",
                        lambda m, p: report(m, 55 + p * 0.40))
                    report("Extrayendo Real-CUGAN...", 95)
                    self._extract_cugan(zip_path)
                except Exception as e:  # CUGAN is optional
                    logger.warning("Real-CUGAN no se pudo descargar: %s", e)
        except Exception as e:
            logger.error("Error descargando modelos: %s", e)
            report(f"Error descargando modelos: {e}", 0)
            return False
        finally:
            shutil.rmtree(work, ignore_errors=True)

        self.exe_path = find_tool("realesrgan-ncnn-vulkan")
        self.cugan_exe_path = find_tool("realcugan-ncnn-vulkan")
        available = self.check_available_models()
        report(f"Modelos disponibles: {len(available)}", 100)
        return self.check_executable() and bool(available)

    def _extract_esrgan(self, zip_path: Path) -> None:
        """exe + OpenMP runtime DLL into SteamWorkshopAppData/, models into models_dir."""
        with zipfile.ZipFile(zip_path) as zf:
            for member in zf.infolist():
                name = Path(member.filename).name
                if member.is_dir() or not name:
                    continue
                if name.endswith((".bin", ".param")):
                    dest = self.models_dir / name
                elif name.lower().endswith((".exe", ".dll")) and "vcomp140d" not in name.lower():
                    dest = DATA_DIR / name
                else:
                    continue  # sample images, demo video, readme
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(zf.read(member))

    @classmethod
    def _extract_cugan(cls, zip_path: Path) -> None:
        """exe + DLL into SteamWorkshopAppData/, plus the model folders the app offers."""
        families = {info["cugan_args"]["model_dir"] for info in cls.MODELS_INFO.values()
                    if info.get("engine") == "realcugan"}
        with zipfile.ZipFile(zip_path) as zf:
            for member in zf.infolist():
                parts = Path(member.filename).parts
                if member.is_dir() or len(parts) < 2:
                    continue
                name = parts[-1]
                if parts[-2] in families and name.endswith((".bin", ".param")):
                    dest = DATA_DIR / parts[-2] / name
                elif name.lower().endswith((".exe", ".dll")):
                    dest = DATA_DIR / name
                else:
                    continue
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(zf.read(member))

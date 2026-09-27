"""processing.base - SteamProcessorBase: init, workspace helpers, tool and GPU discovery."""
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Optional, Tuple

from app_paths import find_tool, resolve
from config import Config
from models import ModelManager
from processing.common import _NO_WINDOW_FLAGS, logger

# One PowerShell call lists the video adapters with their real VRAM.
# Win32_VideoController.AdapterRAM is a 32-bit field (caps at 4 GB), so the
# 64-bit size is read from the display driver's registry key when available.
_GPU_QUERY = r"""
$ErrorActionPreference = 'SilentlyContinue'
$vram = @{}
Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}\0*' |
  ForEach-Object {
    $q = $_.'HardwareInformation.qwMemorySize'
    if ($q -is [byte[]]) { $q = [BitConverter]::ToUInt64($q, 0) }
    if ($q -and $_.DriverDesc) { $vram[$_.DriverDesc] = [uint64]$q }
  }
@(Get-CimInstance Win32_VideoController | ForEach-Object {
    $mem = if ($vram.ContainsKey($_.Name)) { $vram[$_.Name] } else { [uint64]$_.AdapterRAM }
    [pscustomobject]@{ Name = $_.Name; VRAM = $mem }
}) | ConvertTo-Json -Compress
"""

_GPU_VENDORS = ("nvidia", "geforce", "quadro", "amd", "radeon", "intel arc", "arc ")
_VIRTUAL_ADAPTERS = ("basic display", "remote", "virtual", "parsec", "mirror")


class SteamProcessorBase:
    """Main processor for images, video, and GIFs destined for Steam uploads."""

    def __init__(self, config: Config):
        self.config = config
        self.model_manager = ModelManager(
            resolve(config.get("paths.models", "SteamWorkshopAppData/models")))

        self.ffmpeg_path = find_tool("ffmpeg")
        self.gifski_path = find_tool("gifski")
        self.gifsicle_path = find_tool("gifsicle")
        self.realesrgan_path = find_tool("realesrgan-ncnn-vulkan")
        self.realcugan_path = find_tool("realcugan-ncnn-vulkan")
        for name, path in (("FFmpeg", self.ffmpeg_path), ("gifski", self.gifski_path),
                           ("gifsicle", self.gifsicle_path),
                           ("Real-ESRGAN", self.realesrgan_path),
                           ("Real-CUGAN", self.realcugan_path)):
            logger.info("%s: %s", name, path or "no encontrado")

        self._last_split_error = ""
        self._gpu_cache: Optional[Tuple[bool, str]] = None
        self._gifsicle_unavailable = False  # set after a failed download attempt
        self.patch_trailer_for_steam = True

    # ------------------------------------------------------------------
    # Workspace: <stem>_workshop/<category>/ next to the source file
    # ------------------------------------------------------------------
    _WORKSPACE_SUFFIX_TOKEN = "_workshop"
    _WORKSPACE_SUFFIXES = (
        "_AI", "_AI_4x", "_enhanced", "_opt", "_converted",
    )

    def _strip_workspace_suffix(self, stem: str) -> str:
        """Remove processing suffixes and part numbering to recover the original base name."""
        stem = re.sub(r"_part_\d+$", "", stem)
        stem = re.sub(r"_artwork_(main|side)$", "", stem)
        for suffix in self._WORKSPACE_SUFFIXES:
            if stem.endswith(suffix):
                return stem[: -len(suffix)]
        return stem

    def _workspace_root(self, source: Path) -> Path:
        """Return the <stem>_workshop/ folder, climbing up if the source already lives inside one."""
        for parent in source.parents:
            if parent.name.endswith(self._WORKSPACE_SUFFIX_TOKEN):
                return parent
        return source.parent / f"{self._strip_workspace_suffix(source.stem)}{self._WORKSPACE_SUFFIX_TOKEN}"

    def _workspace_dir(self, source: Path, category: str) -> Path:
        """Return (and create) a category subfolder inside the workspace of ``source``."""
        out = self._workspace_root(source) / category
        out.mkdir(parents=True, exist_ok=True)
        return out

    def get_fragments_dir(self, source: Path) -> Path:
        """Folder where the fragments created from ``source`` are written."""
        return self._workspace_root(source) / "fragmentos"

    def list_fragments(self, source: Path, pattern: str = "") -> List[Path]:
        """Fragment images (GIF, JPEG or PNG) of ``source``, optionally filtered by name."""
        frag_dir = self.get_fragments_dir(source)
        if not frag_dir.exists():
            return []
        return sorted(p for p in frag_dir.iterdir()
                      if p.is_file()
                      and p.suffix.lower() in {".gif", ".jpg", ".jpeg", ".png"}
                      and pattern in p.name)

    def read_fragments_manifest(self, source: Path) -> dict:
        """Return the manifest.json written by the last fragmentation of ``source`` ({} if none)."""
        try:
            manifest = self.get_fragments_dir(source) / "manifest.json"
            return json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _archive_before_overwrite(self, out_dir: Path, keep_names: Optional[List[str]] = None,
                                  protect: Optional[Path] = None) -> None:
        """Empty ``out_dir`` before a new run.

        Keeps manifest.json, the names in ``keep_names`` and ``protect`` (the
        source file, in case the user picked a file that lives in this folder).
        """
        if not out_dir.exists():
            return
        keep = set(keep_names or [])
        protected = protect.resolve() if protect else None
        for p in out_dir.iterdir():
            try:
                if protected is not None and p.resolve() == protected:
                    continue
                if p.is_file():
                    if p.name in keep or p.name == "manifest.json":
                        continue
                    p.unlink()
                elif p.is_dir():
                    shutil.rmtree(p, ignore_errors=True)
            except OSError as e:
                logger.warning("No se pudo limpiar %s: %s", p.name, e)

    def _write_manifest(self, out_dir: Path, operacion: str, parametros: dict,
                        archivos: Optional[List[Path]] = None,
                        fuente: Optional[Path] = None) -> None:
        """Write manifest.json describing the run that produced ``out_dir``."""
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
            data = {
                "operacion": operacion,
                "fecha": time.strftime("%Y-%m-%d %H:%M:%S"),
                "fuente": str(fuente) if fuente else None,
                "parametros": parametros,
                "archivos": [
                    {"nombre": p.name,
                     "tamano_mb": round(p.stat().st_size / (1024 * 1024), 3)}
                    for p in (archivos or []) if p and p.exists()
                ],
            }
            (out_dir / "manifest.json").write_text(
                json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        except OSError as e:
            logger.warning("No se pudo escribir manifest: %s", e)

    # ------------------------------------------------------------------
    # Tools and GPU
    # ------------------------------------------------------------------
    def check_ffmpeg(self) -> bool:
        """True when an FFmpeg executable is available."""
        return self.ffmpeg_path is not None and self.ffmpeg_path.exists()

    def check_gifski(self) -> bool:
        """True when gifski (high-quality GIF encoder, optional) is available."""
        return self.gifski_path is not None and self.gifski_path.exists()

    def check_gpu_available(self, force: bool = False) -> Tuple[bool, str]:
        """Return (available, description) of the best GPU. Cached after the first call."""
        if self._gpu_cache is None or force:
            self._gpu_cache = self._detect_gpu()
        return self._gpu_cache

    def _detect_gpu(self) -> Tuple[bool, str]:
        adapters = self._list_video_adapters()
        candidates = [
            (name, vram) for name, vram in adapters
            if any(v in name.lower() for v in _GPU_VENDORS)
            and not any(v in name.lower() for v in _VIRTUAL_ADAPTERS)
        ]
        if candidates:
            name, vram = max(candidates, key=lambda item: item[1])
            if vram >= 512 * 1024 * 1024:
                return True, f"{name} ({vram / 1024 ** 3:.0f} GB VRAM)"
            return True, name
        if self.realesrgan_path is not None:
            # No adapter list (non-Windows or PowerShell blocked): the Vulkan
            # tools still pick a GPU on their own if there is one.
            return True, "GPU Vulkan"
        return False, "No se detecto GPU compatible"

    @staticmethod
    def _list_video_adapters() -> List[Tuple[str, int]]:
        """[(name, vram_bytes)] of the system's video adapters (Windows only)."""
        if sys.platform != "win32":
            return []
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", _GPU_QUERY],
                capture_output=True, text=True, timeout=20, **_NO_WINDOW_FLAGS)
            data = json.loads(result.stdout or "[]")
        except (OSError, subprocess.SubprocessError, ValueError) as e:
            logger.warning("No se pudo consultar la GPU: %s", e)
            return []
        if isinstance(data, dict):
            data = [data]
        adapters = []
        for item in data:
            name = " ".join(str(item.get("Name") or "").split())
            if name:
                adapters.append((name, int(item.get("VRAM") or 0)))
        return adapters

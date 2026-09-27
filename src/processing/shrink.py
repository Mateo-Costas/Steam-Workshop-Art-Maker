"""processing.shrink - fit existing GIFs under a size cap without breaking their timing.

Uses the same shared encoder as the fragmentation (splitting._encode_shared):
all the GIFs of a set get ONE frame rate and quality, so fragments that are
shown side by side on the Steam profile stay in sync.
"""
import shutil
import tempfile
from pathlib import Path
from typing import Callable, List, Optional

from gif_utils import playback_fps
from processing.common import logger
from processing.splitting import _EncodeJob


class ShrinkMixin:
    def shrink_batch_to_size_cap(self, gif_paths: List[Path], max_mb: float = 5.0,
                                 progress_cb: Optional[Callable[[str], None]] = None,
                                 should_cancel: Optional[Callable[[], bool]] = None
                                 ) -> List[Optional[Path]]:
        """Re-encode a set of GIFs so each one is at most ``max_mb``.

        Writes <stem>_opt.gif into each file's workspace "optimizado" folder
        and returns those paths (same order as the input, None on failure).
        Files that already fit are returned unchanged. The encoder always picks
        the best quality that fits.
        """
        paths = [Path(p) for p in gif_paths]
        max_bytes = int(max_mb * 1024 * 1024)
        if not self.check_ffmpeg():
            logger.error("FFmpeg no disponible")
            return [None] * len(paths)
        existing = [p for p in paths if p.exists()]
        if not existing:
            return [None] * len(paths)
        if all(p.stat().st_size <= max_bytes for p in existing):
            _log(progress_cb, f"Todos los archivos ya ocupan como maximo {max_mb:.2f} MB")
            return [p if p.exists() else None for p in paths]

        # The shared rate is the fastest of the set, so no file loses motion.
        fps = max(playback_fps(p) for p in existing)
        work = Path(tempfile.mkdtemp(prefix="wkart_opt_"))
        try:
            jobs = [_EncodeJob(p, "", work / f"{i:02d}_{p.stem}_opt.gif")
                    for i, p in enumerate(existing)]
            _log(progress_cb, f"Optimizando {len(jobs)} archivo(s) a <= {max_mb:.2f} MB "
                              f"(estrategia compartida)")
            result = self._encode_shared(jobs, fps, max_bytes, progress_cb, should_cancel)
            if result is None:
                _log(progress_cb, f"No se consiguio bajar de {max_mb:.2f} MB. "
                                  f"Recorta la duracion del GIF.")
                return [None] * len(paths)

            outputs = {}
            cleaned = set()
            for src, job in zip(existing, jobs):
                out_dir = self._workspace_dir(src, "optimizado")
                if out_dir not in cleaned:
                    self._archive_before_overwrite(
                        out_dir, keep_names=[f"{p.stem}_opt.gif" for p in existing], protect=src)
                    cleaned.add(out_dir)
                dst = out_dir / f"{src.stem}_opt.gif"
                shutil.copyfile(job.output, dst)
                self._patch_gif_trailer(dst)
                self._write_manifest(out_dir, "optimizar_tamano",
                                     {"max_mb": max_mb, "archivos_en_lote": len(existing),
                                      **result},
                                     archivos=[dst], fuente=src)
                outputs[src] = dst
                _log(progress_cb, f"{src.name} -> {dst.name} "
                                  f"({dst.stat().st_size / 1048576:.2f} MB)")
            return [outputs.get(p) for p in paths]
        finally:
            shutil.rmtree(work, ignore_errors=True)



def _log(progress_cb, message: str) -> None:
    logger.info(message)
    if progress_cb:
        try:
            progress_cb(message)
        except Exception:  # a UI callback must never break the optimiser
            pass

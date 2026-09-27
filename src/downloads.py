"""downloads - streaming downloads with progress for the bundled tools and models."""
import logging
from pathlib import Path
from typing import Callable, Optional

import requests

logger = logging.getLogger("WorkshopArt.downloads")

ProgressFn = Optional[Callable[[str, float], None]]


def download_file(url: str, dest: Path, label: str, progress: ProgressFn = None,
                  timeout: float = 90) -> Path:
    """Download ``url`` to ``dest`` (written as .part first, renamed when complete).

    ``progress(message, percent)`` is called at most every 5%. Raises
    requests.RequestException / OSError on failure.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    partial = dest.with_name(dest.name + ".part")
    with requests.get(url, stream=True, timeout=timeout,
                      headers={"User-Agent": "WorkshopArt"}) as response:
        response.raise_for_status()
        total = int(response.headers.get("content-length", 0))
        done, last_step = 0, -1
        with open(partial, "wb") as f:
            for chunk in response.iter_content(chunk_size=256 * 1024):
                f.write(chunk)
                done += len(chunk)
                if progress and total:
                    step = int(done * 20 / total)  # 5 % steps
                    if step != last_step:
                        last_step = step
                        progress(f"{label}: {done / 1048576:.0f}/{total / 1048576:.0f} MB",
                                 done * 100.0 / total)
    partial.replace(dest)
    logger.info("Descargado %s (%.1f MB)", dest.name, dest.stat().st_size / 1048576)
    return dest

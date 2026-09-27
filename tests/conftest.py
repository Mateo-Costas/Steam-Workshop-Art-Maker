"""Shared fixtures: a processor with a throwaway config and small generated media.

The media is generated with the FFmpeg the app uses, so the tests are skipped
when it is not installed (run the app once to download it).
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from app_paths import find_tool  # noqa: E402
from media import make_media  # noqa: E402


@pytest.fixture(scope="session")
def media(tmp_path_factory):
    """Paths to generated test media (created once per test session)."""
    ffmpeg = find_tool("ffmpeg")
    if ffmpeg is None:
        pytest.skip("FFmpeg no está instalado: abre la app una vez para descargarlo")
    return make_media(tmp_path_factory.mktemp("media"), ffmpeg)


@pytest.fixture
def processor(tmp_path):
    """A SteamProcessor using a temporary config.json."""
    from config import Config
    from processing import SteamProcessor
    return SteamProcessor(Config(str(tmp_path / "config.json")))


@pytest.fixture
def work(tmp_path, media):
    """Copy a test file into a fresh folder: work("gif25") -> Path."""
    def copy(name, new_name=None):
        src = media[name]
        dst = tmp_path / "in" / (new_name or src.name)
        dst.parent.mkdir(exist_ok=True)
        dst.write_bytes(src.read_bytes())
        return dst
    return copy

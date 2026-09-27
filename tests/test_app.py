"""Tests of the app logic around the engine: texts, config, models, upload helpers."""
import ast
import json
import re
import string
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Translations
# ---------------------------------------------------------------------------
def _used_text_keys():
    """Every t("key") in the code, plus the families built with f-strings."""
    import processing
    from models import ModelManager
    files = [REPO / "main.py", REPO / "upload_tool.py", *(REPO / "src").rglob("*.py")]
    keys = set()
    for path in files:
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (isinstance(node, ast.Call) and getattr(node.func, "id", None) == "t"
                    and node.args and isinstance(node.args[0], ast.Constant)):
                keys.add(node.args[0].value)
    presets = processing.SteamProcessor.SHOWCASE_PRESETS
    keys |= {f"preset_{p}" for p in presets} | {f"note_{p}" for p in presets}
    keys |= {f"model_desc_{m}" for m in ModelManager.MODELS_INFO}
    return keys


def test_every_text_exists_in_three_languages():
    import i18n
    missing = sorted(_used_text_keys() - set(i18n._STRINGS))
    assert not missing, f"textos sin traducir: {missing}"
    for key, texts in i18n._STRINGS.items():
        assert len(texts) == 3 and all(isinstance(x, str) and x for x in texts), key
        fields = [sorted({f for _, f, _, _ in string.Formatter().parse(x) if f}) for x in texts]
        assert fields[0] == fields[1] == fields[2], f"{key}: huecos distintos {fields}"


def test_language_switch_and_fallbacks():
    import i18n
    try:
        i18n.set_language("EN")
        assert i18n.t("step_file") == "File"
        assert i18n.t("info_size", mb=1.5) == "Size: 1.50 MB"
        assert i18n.t("no_such_key", fallback="x") == "x"
        i18n.set_language("XX")  # ignored
        assert i18n.get_language() == "EN"
    finally:
        i18n.set_language("ES")


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
def test_corrupt_config_is_kept_as_backup(tmp_path):
    from config import Config
    path = tmp_path / "config.json"
    path.write_text("{ esto no es json", encoding="utf-8")
    config = Config(str(path))
    assert config.get("ui.language") == "ES"
    assert (tmp_path / "config.json.bak").exists()
    assert json.loads(path.read_text(encoding="utf-8"))["ui"]["language"] == "ES"


def test_old_config_keys_still_load(tmp_path):
    """A v2.0 config (old keys, absolute paths) merges over the new defaults."""
    from app_paths import resolve
    from config import Config
    path = tmp_path / "config.json"
    old = {"paths": {"ffmpeg": "ffmpeg.exe", "models": str(tmp_path / "m"), "temp_dir": "temp"},
           "steam_profile": {"width": 638, "height": 354, "parts": 5, "min_size_mb": 4.4},
           "ui": {"language": "EN", "is_anime": False, "recent_files": ["x.gif"]}}
    path.write_text(json.dumps(old), encoding="utf-8")
    config = Config(str(path))
    assert config.get("ui.language") == "EN" and config.get("ui.is_anime") is False
    assert config.get("artwork_showcase.main_width") == 506  # new default filled in
    assert resolve(config.get("paths.models")) == tmp_path / "m"
    config.set("ui.scale", 125)
    assert json.loads(path.read_text(encoding="utf-8"))["ui"]["scale"] == 125


def test_relative_paths_resolve_from_the_app_folder():
    from app_paths import APP_DIR, resolve
    assert resolve("SteamWorkshopAppData/models") == APP_DIR / "SteamWorkshopAppData" / "models"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
def test_cugan_leftovers_are_not_listed_as_esrgan_models(tmp_path):
    from models import ModelManager
    for name in ("realesr-animevideov3-x2", "up2x-conservative", "up4x-denoise3x", "my-custom-x2"):
        (tmp_path / f"{name}.bin").write_bytes(b"0")
        (tmp_path / f"{name}.param").write_bytes(b"0")
    available = ModelManager(tmp_path).check_available_models()
    assert "realesr-animevideov3-x2" in available and "my-custom-x2" in available
    assert not [m for m in available if m.startswith("up")]


def test_cugan_extracts_only_the_offered_families(tmp_path, monkeypatch):
    import zipfile
    import models
    monkeypatch.setattr(models, "DATA_DIR", tmp_path)
    archive = tmp_path / "cugan.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        for member in ("pkg/realcugan-ncnn-vulkan.exe", "pkg/vcomp140.dll", "pkg/input.jpg",
                       "pkg/models-se/up2x-no-denoise.bin", "pkg/models-se/up2x-no-denoise.param",
                       "pkg/models-pro/up2x-no-denoise.bin", "pkg/models-nose/up2x-no-denoise.bin"):
            zf.writestr(member, b"0")
    models.ModelManager._extract_cugan(archive)
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "cugan.zip", "models-se", "realcugan-ncnn-vulkan.exe", "vcomp140.dll"]
    assert len(list((tmp_path / "models-se").iterdir())) == 2


def test_model_scales(tmp_path):
    from models import ModelManager
    manager = ModelManager(tmp_path)
    assert manager.model_scale("realesr-animevideov3-x2") == 2
    assert manager.model_scale("realesr-animevideov3-x3") == 3
    assert manager.model_scale("realesrgan-x4plus") == 4
    assert manager.model_scale("RealESRGAN_x2plus") == 2
    assert manager.model_scale("unknown-model") == 4


# ---------------------------------------------------------------------------
# Upload helpers
# ---------------------------------------------------------------------------
def test_console_snippet_per_upload_mode():
    from processing import SteamProcessor
    from ui.logic.common import steam_js_snippet
    for key, cfg in SteamProcessor.SHOWCASE_PRESETS.items():
        assert cfg["upload_hint"] in ("artwork", "screenshot", "workshop"), key
    assert "val(480)" in steam_js_snippet("workshop")
    assert "file_type]').val(3)" in steam_js_snippet("artwork")
    assert "file_type]').val(5)" in steam_js_snippet("screenshot")
    panorama = SteamProcessor.SHOWCASE_PRESETS["panorama_5_630"]
    assert "image_width" in steam_js_snippet(panorama["upload_hint"], panorama.get("spoof_dims"))


@pytest.mark.parametrize("operation, expected", [
    ("showcase_panorama_5_630", "panorama_5_630"),          # v2.1
    ("fragmentar_steam", "workshop_5part"),                 # v2.0
    ("fragmentar_artwork_showcase", "artwork_2part"),       # v2.0
    ("fragmentar_showcase_image_featured_630", "featured_630"),
    ("algo_desconocido", None),
])
def test_preset_is_detected_from_old_and_new_manifests(tmp_path, operation, expected):
    from config import Config
    from processing import SteamProcessor
    from ui.logic.upload import UploadMixin

    class Step4(UploadMixin):
        pass

    step = Step4()
    step.processor = SteamProcessor(Config(str(tmp_path / "config.json")))
    step.current_file = tmp_path / "clip.gif"
    fragments = step.processor.get_fragments_dir(step.current_file)
    fragments.mkdir(parents=True)
    params = {"preset": "panorama_5_630"} if operation.startswith("showcase_") else {}
    (fragments / "manifest.json").write_text(
        json.dumps({"operacion": operation, "parametros": params}), encoding="utf-8")
    assert step.current_fragments_preset() == expected


def test_upload_tool_arguments():
    from upload_tool import parse_cli_args
    files, preset = parse_cli_args(["--fragments", "a.gif", "b.gif", "--preset", "artwork_2part"])
    assert [f.name for f in files] == ["a.gif", "b.gif"] and preset == "artwork_2part"
    assert parse_cli_args(["--preset", "workshop_5part"]) == ([], "workshop_5part")
    assert parse_cli_args([]) == ([], None)


def test_upload_tool_knows_every_preset():
    from processing import SteamProcessor
    from upload_tool import UPLOAD_PRESETS
    assert set(SteamProcessor.SHOWCASE_PRESETS) <= set(UPLOAD_PRESETS)
    assert UPLOAD_PRESETS["panorama_5_630"][1] is True  # size spoof on


def test_cookie_banner_asks_to_install_only_when_missing(monkeypatch):
    import steam_uploader
    from upload_tool import UploadApp
    shown = {}
    banner = type("Banner", (), {"configure": lambda self, **kwargs: shown.update(kwargs)})()
    monkeypatch.setattr(steam_uploader, "cookies_source", lambda: "none")
    for installed in (True, False):
        monkeypatch.setattr(steam_uploader, "browser_cookies_available", lambda: installed)
        UploadApp._update_cookie_banner(type("App", (), {"banner": banner})())
        assert ("instala browser_cookie3" in shown["text"]) is not installed
        assert "Firefox" in shown["text"] and "Chrome" not in shown["text"]


def test_uploader_reads_sizes_of_patched_gifs(tmp_path, media):
    from steam_uploader import _image_size
    patched = tmp_path / "patched.gif"
    patched.write_bytes(media["gif25"].read_bytes()[:-1] + b"\x21")
    assert _image_size(patched) == (320, 180)
    assert _image_size(media["image"]) == (1200, 800)


def test_no_leftover_references_to_removed_modules():
    removed = re.compile(r"\b(_pro_features|theme_PRO|gui_methods|analyzers|moviepy)\b")
    for path in [REPO / "main.py", REPO / "upload_tool.py", *(REPO / "src").rglob("*.py")]:
        text = path.read_text(encoding="utf-8")
        if path.name == "video_utils.py":
            text = text.replace("former moviepy dependency", "")
        assert not removed.search(text), path

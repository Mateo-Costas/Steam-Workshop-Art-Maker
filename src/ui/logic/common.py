"""ui.logic.common - shared constants and helpers for the logic mixins."""
from typing import Optional

from i18n import t
from video_utils import IMAGE_EXTS, MEDIA_EXTS, VIDEO_EXTS

__all__ = ["IMAGE_EXTS", "MEDIA_EXTS", "VIDEO_EXTS", "STEAM_UPLOAD_URL",
           "steam_js_snippet", "steam_format_suggestion"]

#: Steam page where artwork, screenshots and workshop items are uploaded.
STEAM_UPLOAD_URL = "https://steamcommunity.com/sharedfiles/edititem/767/3/"

# Browser-console snippets for the upload page, per upload mode. The panorama
# variant also fakes the image size so Steam doesn't reject the wide banner.
_JS_BY_MODE = {
    "workshop": ("$J('[name=consumer_app_id]').val(480);\n"
                 "$J('[name=file_type]').val(0);\n"
                 "$J('[name=visibility]').val(0);"),
    "artwork": ("$J('[name=consumer_app_id]').val(767);\n"
                "$J('[name=file_type]').val(3);\n"
                "$J('[name=visibility]').val(0);"),
    "screenshot": ("$J('[name=consumer_app_id]').val(767);\n"
                   "$J('[name=file_type]').val(5);\n"
                   "$J('[name=visibility]').val(0);"),
}
_JS_SPOOF_DIMS = ("$J('#image_width').val(1000).attr('id', '');\n"
                  "$J('#image_height').val(1).attr('id', '');\n")


def steam_js_snippet(upload_hint: str = "workshop", spoof_dims: bool = False) -> str:
    """Console snippet for a preset's upload mode ("workshop", "artwork", "screenshot")."""
    snippet = _JS_BY_MODE.get(upload_hint, _JS_BY_MODE["artwork"])
    return _JS_SPOOF_DIMS + snippet if spoof_dims else snippet


def steam_format_suggestion(w: int, h: int) -> Optional[str]:
    """Preset that best fits an image of w x h (shown in the file info panel)."""
    if w <= 0 or h <= 0:
        return None
    ratio = w / h
    if ratio >= 6.0:
        return t("preset_panorama_5_630", fallback="Panorama · banner ultra-ancho")
    if ratio >= 3.5:
        return t("preset_artwork_4grid", fallback="Artwork 4-grid · cuadrícula")
    if ratio >= 1.5:
        return t("preset_workshop_5part", fallback="Workshop Showcase · 5 partes")
    if ratio >= 0.8:
        return t("preset_artwork_2part", fallback="Artwork Main + Side")
    return t("preset_featured_630", fallback="Featured Artwork · 1 slot destacado")

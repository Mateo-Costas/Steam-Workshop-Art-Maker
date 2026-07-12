"""ui.theme - design tokens for the WorkshopArt interface.

Re-exports the WCAG-AA-verified palette from theme_PRO and adds a
user-configurable font scale (accessibility, WCAG 1.4.4). The scale is read
from config (``ui.scale``) once at startup; changing it requires an app
restart, which keeps layout code free of live re-flow complexity.

Usage:
    from ui import theme
    theme.init_scale(config)                      # once, before building the UI
    label = ctk.CTkLabel(parent, font=theme.font("BODY"))
"""
from theme_PRO import Colors  # noqa: F401  (re-exported design token)

# Base font sizes before scaling. Segoe UI ships with every supported
# Windows version; Consolas is the monospace counterpart.
_BASE_FONTS: dict[str, tuple[str, int, str]] = {
    "TITLE":      ("Segoe UI", 22, "bold"),
    "HEADING":    ("Segoe UI", 14, "bold"),
    "SUBHEADING": ("Segoe UI", 12, "bold"),
    "BODY":       ("Segoe UI", 12, ""),
    "SMALL":      ("Segoe UI", 11, ""),
    "CAPTION":    ("Segoe UI", 10, ""),
    "MONO":       ("Consolas", 11, ""),
    "MONO_SMALL": ("Consolas", 10, ""),
}

#: Font-scale options offered in the header selector, as percentages.
SCALE_OPTIONS: tuple[int, ...] = (100, 125, 150)

_scale: float = 1.0


class Spacing:
    """Spacing scale in pixels. Use these instead of magic pad numbers."""

    XS = 4
    SM = 8
    MD = 12
    LG = 20
    XL = 32


#: Minimum height for clickable controls (touch/motor accessibility).
MIN_BUTTON_HEIGHT = 36


def init_scale(config) -> None:
    """Read the persisted font scale from config (``ui.scale``, percent)."""
    global _scale
    try:
        pct = int(config.get("ui.scale", 100))
    except (TypeError, ValueError):
        pct = 100
    if pct not in SCALE_OPTIONS:
        pct = 100
    _scale = pct / 100.0


def get_scale_percent() -> int:
    """Return the active font scale as a percentage (100, 125 or 150)."""
    return int(round(_scale * 100))


def font(token: str) -> tuple:
    """Return a tkinter font tuple for a token, scaled by the user setting.

    Args:
        token: One of the keys in ``_BASE_FONTS`` (e.g. "BODY", "HEADING").

    Raises:
        KeyError: If the token is unknown (programming error, fail loudly).
    """
    family, size, weight = _BASE_FONTS[token]
    scaled = max(8, round(size * _scale))
    return (family, scaled, weight) if weight else (family, scaled)

"""ui.theme - design tokens for the WorkshopArt interface.

Colors: GitHub-dark palette; text colors meet WCAG AA against BG_PRIMARY.
Fonts: font(token) returns a tkinter font tuple scaled by the user setting
(``ui.scale``, WCAG 1.4.4). The scale is read once at startup; changing it
requires an app restart, which keeps layout code free of live re-flow.

Usage:
    from ui import theme
    theme.init_scale(config)                      # once, before building the UI
    label = ctk.CTkLabel(parent, font=theme.font("BODY"))
"""


class Colors:
    """Central color palette (GitHub dark)."""

    # Background layers - darker = lower in the visual hierarchy
    BG_PRIMARY = "#0d1117"     # main window background
    BG_SECONDARY = "#161b22"   # panels, status bar
    BG_TERTIARY = "#21262d"    # inputs, cards
    BG_ELEVATED = "#2d333b"    # dropdowns, tooltips

    # Accents
    ACCENT = "#58a6ff"         # primary buttons, active step, links
    ACCENT_DARK = "#1f6feb"    # hover state for ACCENT elements
    SUCCESS = "#3fb950"
    WARNING = "#d29922"
    DANGER = "#f85149"

    # Text - contrast ratios against BG_PRIMARY
    TEXT = "#f0f6fc"           # 16.1:1 (AAA)
    TEXT_SECONDARY = "#adbac7"  # 10.0:1 (AAA)
    TEXT_MUTED = "#8b949e"     # 6.3:1  (AA)

    BORDER = "#30363d"
    HOVER = "#30363d"


#: Same palette as a dict, for the non-CustomTkinter windows (quality report).
PALETTE = {
    "bg_primary": Colors.BG_PRIMARY,
    "bg_secondary": Colors.BG_SECONDARY,
    "bg_tertiary": Colors.BG_TERTIARY,
    "accent_primary": Colors.ACCENT,
    "accent_success": Colors.SUCCESS,
    "accent_warning": Colors.WARNING,
    "accent_danger": Colors.DANGER,
    "text_primary": Colors.TEXT,
    "text_secondary": Colors.TEXT_SECONDARY,
}

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

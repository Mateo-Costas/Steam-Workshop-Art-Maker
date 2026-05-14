"""
theme_PRO.py - Color palette and font constants for the UI.

Defines Colors (GitHub Dark-inspired) and Fonts used throughout
the CustomTkinter interface. Also provides ModernTheme and
ModernThemePro as dict-based aliases for legacy code that
references theme colors by string key instead of class attribute.
"""


class Colors:
    """Central color palette — GitHub Dark style.

    All text colors have been verified against BG_PRIMARY to meet
    WCAG AA contrast requirements (4.5:1 for normal text).
    """

    # Background layers — darker = lower in the visual hierarchy
    BG_PRIMARY   = "#0d1117"   # main window background
    BG_SECONDARY = "#161b22"   # sidebar, status bar, panel backgrounds
    BG_TERTIARY  = "#21262d"   # input fields, dropdown backgrounds
    BG_ELEVATED  = "#2d333b"   # floating elements (dropdowns, tooltips)

    # Interactive accent colors
    ACCENT      = "#58a6ff"    # primary buttons, active tabs, links
    ACCENT_DARK = "#1f6feb"    # hover state for ACCENT elements
    SUCCESS     = "#3fb950"    # positive indicators (GPU found, done)
    WARNING     = "#d29922"    # non-critical alerts
    DANGER      = "#f85149"    # destructive actions, errors

    # Text — contrast ratios against BG_PRIMARY
    TEXT           = "#f0f6fc"   # 16.1:1 (WCAG AAA)
    TEXT_SECONDARY = "#adbac7"   # 10.0:1 (WCAG AAA)
    TEXT_MUTED     = "#8b949e"   # 6.3:1  (WCAG AA)

    # Borders
    BORDER       = "#30363d"
    BORDER_FOCUS = "#58a6ff"   # keyboard-focus ring

    # Interaction states
    HOVER  = "#30363d"
    ACTIVE = "#21262d"


class Fonts:
    """Font size scale — minimum sizes chosen for WCAG 1.4.4 readability."""

    TITLE      = ("Segoe UI", 22, "bold")
    HEADING    = ("Segoe UI", 14, "bold")
    BODY       = ("Segoe UI", 12)
    SMALL      = ("Segoe UI", 11)
    CAPTION    = ("Segoe UI", 10)
    MONO       = ("Consolas", 11)
    MONO_SMALL = ("Consolas", 10)


# ---------------------------------------------------------------------------
# Dict-based aliases kept for backward compatibility.
# New code should reference Colors/Fonts attributes directly.
# ---------------------------------------------------------------------------

class ModernTheme:
    """Legacy color dict — wraps Colors class attributes as string keys."""
    COLORS = {
        "bg_dark":        Colors.BG_PRIMARY,
        "bg_medium":      Colors.BG_SECONDARY,
        "bg_light":       Colors.BG_TERTIARY,
        "accent":         Colors.ACCENT,
        "success":        Colors.SUCCESS,
        "warning":        Colors.WARNING,
        "error":          Colors.DANGER,
        "text_primary":   Colors.TEXT,
        "text_secondary": Colors.TEXT_SECONDARY,
        "border":         Colors.BORDER,
    }


class ModernThemePro:
    """Extended color dict used by QualityReportSystem and legacy subsystems."""
    COLORS = {
        # Backgrounds
        "bg_primary":   Colors.BG_PRIMARY,
        "bg_secondary": Colors.BG_SECONDARY,
        "bg_tertiary":  Colors.BG_TERTIARY,
        "bg_elevated":  Colors.BG_ELEVATED,
        # Accents
        "accent_primary":   Colors.ACCENT,
        "accent_secondary": Colors.ACCENT_DARK,
        "accent_success":   Colors.SUCCESS,
        "accent_warning":   Colors.WARNING,
        "accent_danger":    Colors.DANGER,
        # Text
        "text_primary":   Colors.TEXT,
        "text_secondary": Colors.TEXT_SECONDARY,
        "text_tertiary":  Colors.TEXT_MUTED,
        "text_accent":    Colors.ACCENT,
        # Borders
        "border_primary":   Colors.BORDER,
        "border_secondary": Colors.BG_TERTIARY,
        "border_focus":     Colors.BORDER_FOCUS,
        # States
        "hover_overlay":    Colors.HOVER,
        "active_overlay":   Colors.ACTIVE,
        "disabled_overlay": Colors.BG_SECONDARY,
        # Gradient compat keys (used by older PRO components)
        "gradient_start":  Colors.ACCENT_DARK,
        "gradient_middle": "#2d7de8",
        "gradient_end":    Colors.ACCENT,
        # Shadow compat keys
        "shadow_light":  "#000000",
        "shadow_medium": Colors.BG_PRIMARY,
        "shadow_heavy":  "#010409",
    }

    @classmethod
    def apply_modern_theme(cls, root):
        """No-op stub. CustomTkinter handles its own theming internally."""
        pass


# Merge ModernThemePro into ModernTheme so both dicts are equivalent
ModernTheme.COLORS.update(ModernThemePro.COLORS)

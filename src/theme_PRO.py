"""
theme_PRO.py - Sistema de colores y constantes visuales
Compatible con CustomTkinter
"""


class Colors:
    """Paleta de colores del proyecto (GitHub Dark style)."""

    # Fondos
    BG_PRIMARY = "#0d1117"
    BG_SECONDARY = "#161b22"
    BG_TERTIARY = "#21262d"
    BG_ELEVATED = "#2d333b"

    # Acentos
    ACCENT = "#58a6ff"
    ACCENT_DARK = "#1f6feb"
    SUCCESS = "#3fb950"
    WARNING = "#d29922"
    DANGER = "#f85149"

    # Texto — contrastes verificados contra BG_PRIMARY para cumplir WCAG AA
    TEXT = "#f0f6fc"           # 16.1:1  (AAA)
    TEXT_SECONDARY = "#adbac7"  # 10.0:1 (AAA) — antes 8b949e (6.3:1)
    TEXT_MUTED = "#8b949e"      # 6.3:1  (AA normal, AAA grande) — antes 6e7681 (4.4:1)

    # Bordes
    BORDER = "#30363d"
    BORDER_FOCUS = "#58a6ff"   # anillo de foco visible para navegación por teclado

    # Hover / Active
    HOVER = "#30363d"
    ACTIVE = "#21262d"


class Fonts:
    """Fuentes del proyecto.
    Tamaños mínimos subidos para legibilidad (WCAG 1.4.4 — texto redimensionable).
    """
    TITLE = ("Segoe UI", 22, "bold")
    HEADING = ("Segoe UI", 14, "bold")
    BODY = ("Segoe UI", 12)
    SMALL = ("Segoe UI", 11)   # antes 10
    CAPTION = ("Segoe UI", 10)  # antes 9 (demasiado pequeño)
    MONO = ("Consolas", 11)    # antes 10
    MONO_SMALL = ("Consolas", 10)  # antes 9


# ---------------------------------------------------------------------------
# Aliases de compatibilidad para que el codigo viejo no rompa
# ---------------------------------------------------------------------------

class ModernTheme:
    COLORS = {
        "bg_dark": Colors.BG_PRIMARY,
        "bg_medium": Colors.BG_SECONDARY,
        "bg_light": Colors.BG_TERTIARY,
        "accent": Colors.ACCENT,
        "success": Colors.SUCCESS,
        "warning": Colors.WARNING,
        "error": Colors.DANGER,
        "text_primary": Colors.TEXT,
        "text_secondary": Colors.TEXT_SECONDARY,
        "border": Colors.BORDER,
    }


class ModernThemePro:
    COLORS = {
        # Fondos
        "bg_primary": Colors.BG_PRIMARY,
        "bg_secondary": Colors.BG_SECONDARY,
        "bg_tertiary": Colors.BG_TERTIARY,
        "bg_elevated": Colors.BG_ELEVATED,
        # Acentos
        "accent_primary": Colors.ACCENT,
        "accent_secondary": Colors.ACCENT_DARK,
        "accent_success": Colors.SUCCESS,
        "accent_warning": Colors.WARNING,
        "accent_danger": Colors.DANGER,
        # Texto
        "text_primary": Colors.TEXT,
        "text_secondary": Colors.TEXT_SECONDARY,
        "text_tertiary": Colors.TEXT_MUTED,
        "text_accent": Colors.ACCENT,
        # Bordes
        "border_primary": Colors.BORDER,
        "border_secondary": Colors.BG_TERTIARY,
        "border_focus": Colors.BORDER_FOCUS,
        # Estados
        "hover_overlay": Colors.HOVER,
        "active_overlay": Colors.ACTIVE,
        "disabled_overlay": Colors.BG_SECONDARY,
        # Gradientes (compat)
        "gradient_start": Colors.ACCENT_DARK,
        "gradient_middle": "#2d7de8",
        "gradient_end": Colors.ACCENT,
        # Sombras (compat)
        "shadow_light": "#000000",
        "shadow_medium": Colors.BG_PRIMARY,
        "shadow_heavy": "#010409",
    }

    @classmethod
    def apply_modern_theme(cls, root):
        """No-op: CustomTkinter maneja su propio tema."""
        pass


# Mantener alias de colores cruzado
ModernTheme.COLORS.update(ModernThemePro.COLORS)

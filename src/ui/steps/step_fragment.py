"""ui.steps.step_fragment - step 3: choose a Steam preset and fragment."""
import tkinter as tk

import customtkinter as ctk

from i18n import t
from ui import theme
from ui.theme import Colors, Spacing
from ui.widgets import PresetCard, attach_tooltip, darken

#: Catalogue sections: (title key, fallback, preset keys). Titles, notes and
#: dimensions of each preset come from i18n and SteamProcessor.preset_config.
_SECTIONS = (
    ("section_workshop_banner", "WORKSHOP SHOWCASE · BANNER ANIMADO", ("workshop_5part",)),
    ("section_artwork", "ARTWORK SHOWCASE",
     ("artwork_2part", "featured_630", "artwork_single_630", "artwork_4grid", "panorama_5_630")),
    ("section_screenshot", "SCREENSHOT SHOWCASE", ("screenshot_638", "screenshot_4grid")),
    ("section_workshop_grid", "WORKSHOP SHOWCASE · CUADRADOS",
     ("workshop_5slot_150", "workshop_5slot_119")),
)


def preset_dimensions(cfg: dict) -> str:
    """Human description of a preset's pixel layout, e.g. "5 × 127 × 354 px · total 638 × 354"."""
    widths = [w for _name, w, _left in cfg["parts"]]
    height = cfg["fixed_h"]
    if not height:
        return t("dims_free_height", fallback="{widths} px de ancho · alto libre",
                 widths=" + ".join(str(w) for w in widths))
    if len(widths) == 1:
        return f"{widths[0]} × {height} px"
    if len(set(widths)) == 1:
        text = f"{len(widths)} × {widths[0]} × {height} px"
    else:
        text = " + ".join(str(w) for w in widths) + f" × {height} px"
    return f"{text}  ·  total {cfg['total_w']} × {height}"


class FragmentStep(ctk.CTkFrame):
    """Preset cards for every Steam showcase layout plus the fragment actions."""

    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self._app = app
        self._preset_var = tk.StringVar(value="workshop_5part")

        catalog = ctk.CTkScrollableFrame(self, fg_color=Colors.BG_SECONDARY, corner_radius=10)
        catalog.pack(fill="both", expand=True, padx=Spacing.LG, pady=Spacing.MD)
        for title_key, fallback, presets in _SECTIONS:
            ctk.CTkLabel(catalog, text=t(title_key, fallback=fallback), font=theme.font("CAPTION"),
                         text_color=Colors.TEXT_MUTED).pack(anchor="w", padx=Spacing.SM,
                                                             pady=(Spacing.MD, 2))
            for key in presets:
                PresetCard(catalog, key, app.preset_title(key), self._preset_var,
                           dims=preset_dimensions(app.processor.preset_config(key)),
                           note=t(f"note_{key}", fallback=""),
                           badge=t("most_used", fallback="MÁS USADO") if key == "workshop_5part" else ""
                           ).pack(fill="x", padx=Spacing.XS, pady=2)

        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.pack(fill="x", padx=Spacing.LG, pady=(0, Spacing.MD))
        buttons = (
            (t("fragment_now", fallback="Fragmentar"),
             lambda: app.fragment_with_preset(self._preset_var.get()), Colors.DANGER,
             t("tip_fragment_steam", fallback="Cortar en piezas listas para Steam (máx. 5 MB cada una)")),
            (t("open_preview", fallback="Preview de fragmentos"),
             lambda: app._open_fragment_preview(self._preset_var.get()), Colors.ACCENT,
             t("tip_open_preview", fallback="Ver cómo quedará el corte antes de fragmentar")),
            ("⚡ " + t("pipeline_one_click", fallback="Pipeline 1-clic"),
             lambda: app.run_full_pipeline(self._preset_var.get()), "#8957e5",
             t("tip_pipeline", fallback="Todo automático: IA + colores + fragmentar")),
            (t("optimize_size", fallback="Optimizar ≤ 5 MB"), app.optimize_to_steam_limit, Colors.SUCCESS,
             t("tip_optimize_size", fallback="Reducir GIF que ya tengas por debajo de 5 MB sin desincronizarlos")),
        )
        for text, command, color, tip in buttons:
            btn = ctk.CTkButton(actions, text=text, command=command,
                                fg_color=color, hover_color=darken(color),
                                height=theme.MIN_BUTTON_HEIGHT, corner_radius=8,
                                font=theme.font("SMALL"))
            btn.pack(side="left", expand=True, fill="x", padx=Spacing.XS)
            attach_tooltip(btn, tip)

    def set_compact(self, compact: bool) -> None:
        """Single-column layout already; nothing to reflow."""

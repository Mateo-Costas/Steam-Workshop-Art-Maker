"""ui.steps.step_fragment - step 3: choose a Steam preset and fragment."""
import tkinter as tk

import customtkinter as ctk

from i18n import t
from ui import theme
from ui.theme import Colors, Spacing
from ui.widgets import PresetCard, attach_tooltip, darken


class FragmentStep(ctk.CTkFrame):
    """Preset cards for every Steam showcase layout plus the fragment actions.

    Routing mirrors the old fragment_for_steam dialog:
        workshop_5part -> app._fragment_workshop_flow()  (PRO adds preview)
        artwork_2part  -> app.fragment_for_artwork_direct()
        anything else  -> app.fragment_for_showcase_preset(key)
    """

    #: (section, [(key, title, dims, note, badge), ...]) - presentation copy
    #: for SteamProcessor.SHOWCASE_PRESETS plus the 5-part workshop banner.
    _CATALOG = (
        ("WORKSHOP SHOWCASE — BANNER ANIMADO", (
            ("workshop_5part", "Workshop Showcase · 5 partes horizontales",
             "5 × 638 × 354 px  |  total: 3190 × 354",
             "Formato principal para GIFs animados en el perfil de Steam",
             "MAS USADO"),
        )),
        ("ARTWORK SHOWCASE", (
            ("artwork_2part", "Main + Side (recomendado)",
             "506 px main + 100 px side  |  alto libre",
             "Diseño clásico de 2 columnas · acepta GIFs y estáticos", ""),
            ("featured_630", "Featured Artwork · 1 slot destacado",
             "630 × H  |  alto libre",
             "Imagen/GIF grande en la parte superior del perfil", ""),
            ("artwork_single_630", "Artwork Single · 16:9",
             "630 × 354 px  |  1 slot",
             "Un único GIF o imagen en proporción 16:9", ""),
            ("artwork_4grid", "Artwork 4-grid · cuadrícula",
             "4 × 245 × 245 px  |  total: 980 × 245",
             "Cuatro cuadrados iguales formando un banner", ""),
            ("panorama_5_630", "Panorama · banner ultra-ancho",
             "5 × 630 × 360 px  |  total: 3150 × 360",
             "Banner horizontal ancho de 5 piezas", ""),
        )),
        ("SCREENSHOT SHOWCASE", (
            ("screenshot_638", "Screenshot Simple · 1 slot",
             "638 × 354 px  |  file_type=5",
             "Una sola captura animada en el showcase de screenshots", ""),
            ("screenshot_4grid", "Screenshot 4-grid",
             "4 × 638 × 354 px  |  total: 2552 × 354",
             "Cuatro screenshots formando una tira horizontal", ""),
        )),
        ("WORKSHOP SHOWCASE — CUADRADOS", (
            ("workshop_5slot_150", "Workshop Grid · 5 × 150 px",
             "5 × 150 × 150 px  |  total: 750 × 150",
             "Tamaño de upload recomendado, sin bordes negros", ""),
            ("workshop_5slot_119", "Workshop Grid · 5 × 119 px (nativo)",
             "5 × 119 × 119 px  |  total: 595 × 119",
             "Tamaño de display nativo de Steam Workshop", ""),
        )),
    )

    def __init__(self, parent, app, preview_available: bool):
        super().__init__(parent, fg_color="transparent")
        self._app = app
        self._preset_var = tk.StringVar(value="workshop_5part")

        catalog = ctk.CTkScrollableFrame(self, fg_color=Colors.BG_SECONDARY,
                                         corner_radius=10)
        catalog.pack(fill="both", expand=True, padx=Spacing.LG, pady=Spacing.MD)
        for section, presets in self._CATALOG:
            ctk.CTkLabel(catalog, text=section, font=theme.font("CAPTION"),
                         text_color=Colors.TEXT_MUTED).pack(
                anchor="w", padx=Spacing.SM, pady=(Spacing.MD, 2))
            for key, title, dims, note, badge in presets:
                PresetCard(catalog, key, title, self._preset_var,
                           dims=dims, note=note, badge=badge).pack(
                    fill="x", padx=Spacing.XS, pady=2)

        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.pack(fill="x", padx=Spacing.LG, pady=(0, Spacing.MD))

        fragment_btn = ctk.CTkButton(
            actions, text=t("fragment_now", fallback="Fragmentar"),
            command=self._fragment_selected,
            fg_color=Colors.DANGER, hover_color=darken(Colors.DANGER),
            height=theme.MIN_BUTTON_HEIGHT, corner_radius=8,
            font=theme.font("SMALL"))
        fragment_btn.pack(side="left", expand=True, fill="x", padx=Spacing.XS)
        attach_tooltip(fragment_btn, t("tip_fragment_steam",
                                       fallback="Cortar en piezas listas para Steam"))

        if preview_available:
            preview_btn = ctk.CTkButton(
                actions, text=t("open_preview", fallback="Preview de fragmentos"),
                command=app._open_fragment_preview,
                fg_color=Colors.ACCENT, hover_color=darken(Colors.ACCENT),
                height=theme.MIN_BUTTON_HEIGHT, corner_radius=8,
                font=theme.font("SMALL"))
            preview_btn.pack(side="left", expand=True, fill="x", padx=Spacing.XS)
            attach_tooltip(preview_btn, t("tip_open_preview",
                                          fallback="Ver como quedara fragmentado antes de cortar"))

        optimize_btn = ctk.CTkButton(
            actions, text=t("optimize_size", fallback="Optimizar ≤ 5 MB"),
            command=app.optimize_to_steam_limit,
            fg_color=Colors.SUCCESS, hover_color=darken(Colors.SUCCESS),
            height=theme.MIN_BUTTON_HEIGHT, corner_radius=8,
            font=theme.font("SMALL"))
        optimize_btn.pack(side="left", expand=True, fill="x", padx=Spacing.XS)
        attach_tooltip(optimize_btn, t("tip_optimize_size",
                                       fallback="Reducir GIFs al limite de 5 MB de Steam"))

    def _fragment_selected(self) -> None:
        """Route the selected preset to the matching fragmentation flow."""
        key = self._preset_var.get()
        if key == "workshop_5part":
            self._app._fragment_workshop_flow()
        elif key == "artwork_2part":
            self._app.fragment_for_artwork_direct()
        else:
            self._app.fragment_for_showcase_preset(key)

    def set_compact(self, compact: bool) -> None:
        """Single-column layout already; nothing to reflow."""

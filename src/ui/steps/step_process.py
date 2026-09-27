"""ui.steps.step_process - step 2: AI model, color adjustments and processing actions."""
import customtkinter as ctk

from i18n import t
from ui import theme
from ui.color_preview import ColorPreviewPanel
from ui.theme import Colors, Spacing
from ui.widgets import SliderRow, attach_tooltip, darken, section_label


class ProcessStep(ctk.CTkFrame):
    """AI engine selection, color adjustments and the processing actions.

    Exposes on the app (contract with ui.logic.system.SystemMixin):
        app.model_combo:      AI model selector.
        app.model_info_frame: panel refreshed by update_model_info().
    """

    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self._app = app

        self.grid_columnconfigure((0, 1), weight=1, uniform="cols")
        self.grid_rowconfigure(0, weight=1)

        self._left = self._build_engine_column()
        self._left.grid(row=0, column=0, sticky="nsew",
                        padx=(Spacing.LG, Spacing.SM), pady=Spacing.MD)
        self._right = self._build_adjustments_column()
        self._right.grid(row=0, column=1, sticky="nsew",
                         padx=(Spacing.SM, Spacing.LG), pady=Spacing.MD)
        self._actions = self._build_actions_row()
        self._actions.grid(row=1, column=0, columnspan=2, sticky="ew",
                           padx=Spacing.LG, pady=(0, Spacing.MD))

    # ------------------------------------------------------------------
    # Columns
    # ------------------------------------------------------------------
    def _build_engine_column(self) -> ctk.CTkFrame:
        app = self._app
        col = ctk.CTkScrollableFrame(self, fg_color=Colors.BG_SECONDARY, corner_radius=10)

        section_label(col, t("ai_model", fallback="Modelo de IA"))
        app.model_combo = ctk.CTkComboBox(
            col, variable=app.model_var, height=32, state="readonly",
            fg_color=Colors.BG_TERTIARY, border_color=Colors.BORDER,
            button_color=Colors.ACCENT, dropdown_fg_color=Colors.BG_ELEVATED,
            font=theme.font("SMALL"),
            command=lambda _v: app.update_model_info())
        app.model_combo.pack(fill="x", padx=Spacing.SM, pady=(0, Spacing.XS))
        app.model_info_frame = ctk.CTkFrame(col, fg_color="transparent")
        app.model_info_frame.pack(fill="x", padx=Spacing.SM, pady=(0, Spacing.SM))

        section_label(col, t("processing_section", fallback="Procesamiento"))
        gpu_switch = ctk.CTkSwitch(col, text=t("use_gpu", fallback="Usar GPU"),
                                   variable=app.gpu_var, font=theme.font("SMALL"),
                                   progress_color=Colors.SUCCESS)
        gpu_switch.pack(anchor="w", padx=Spacing.SM, pady=(0, Spacing.SM))
        attach_tooltip(gpu_switch, t("tip_use_gpu", fallback="La GPU es de 5 a 10 veces más rápida que la CPU"))

        enhance = ctk.CTkCheckBox(col, text=t("enhance_colors", fallback="Aplicar ajustes de color tras la IA"),
                                  variable=app.enhance_colors_var, font=theme.font("SMALL"),
                                  checkbox_width=18, checkbox_height=18)
        enhance.pack(anchor="w", padx=Spacing.SM, pady=(2, Spacing.SM))
        attach_tooltip(enhance, t("tip_enhance_colors",
                                  fallback="Usa los ajustes de la derecha al terminar la IA y en el pipeline"))
        return col

    def _build_adjustments_column(self) -> ctk.CTkFrame:
        app = self._app
        col = ctk.CTkScrollableFrame(self, fg_color=Colors.BG_SECONDARY, corner_radius=10)
        section_label(col, t("live_preview", fallback="Preview en vivo"))
        self.color_preview = ColorPreviewPanel(col, app)
        self.color_preview.pack(fill="x", padx=Spacing.SM)

        section_label(col, t("color_adjustments", fallback="Ajustes de color"))
        rows = (
            (t("contrast", fallback="Contraste"), app.contrast_var, 0.5, 2.0, "{:.1f}", Colors.ACCENT),
            (t("saturation", fallback="Saturación"), app.saturation_var, 0.5, 2.0, "{:.1f}", Colors.ACCENT),
            (t("vibrance", fallback="Vibrance"), app.vibrance_var, 0.0, 1.0, "{:.2f}", "#a855f7"),
            (t("sharpness", fallback="Nitidez"), app.sharpness_var, 0.0, 1.0, "{:.2f}", "#f59e0b"),
            (t("temperature", fallback="Temperatura"), app.temperature_var, -1.0, 1.0, "{:+.2f}", "#ef4444"),
        )
        for label, var, lo, hi, fmt, color in rows:
            SliderRow(col, label, var, lo, hi, fmt=fmt, color=color).pack(
                fill="x", padx=Spacing.SM, pady=(0, Spacing.SM))
        return col

    def _build_actions_row(self) -> ctk.CTkFrame:
        app = self._app
        row = ctk.CTkFrame(self, fg_color="transparent")
        buttons = (
            (t("process_ai", fallback="Procesar con IA"), app.process_full_ai, Colors.ACCENT,
             t("tip_process_ai", fallback="Mejorar la resolución con Real-ESRGAN / Real-CUGAN")),
            (t("colors_only", fallback="Solo colores"), app.enhance_colors_only, Colors.SUCCESS,
             t("tip_colors_only", fallback="Aplicar los ajustes de color sin IA (rápido)")),
            (t("mp4_to_gif", fallback="Video → GIF"), app.convert_mp4_to_gif, Colors.WARNING,
             t("tip_mp4_to_gif", fallback="Convertir un video a GIF con recorte y FPS a elegir")),
            (t("enhance_animation", fallback="Mejorar animación"), app.enhance_animation, "#e67e22",
             t("tip_enhance_animation", fallback="Interpolar frames con RIFE para una animación más fluida")),
            (t("download_models", fallback="Descargar modelos"), app.download_models, Colors.BG_TERTIARY,
             t("tip_download_models", fallback="Descargar los modelos de IA (unos 90 MB)")),
        )
        for text, command, color, tip in buttons:
            btn = ctk.CTkButton(row, text=text, command=command,
                                fg_color=color, hover_color=darken(color),
                                height=theme.MIN_BUTTON_HEIGHT, corner_radius=8,
                                font=theme.font("SMALL"))
            btn.pack(side="left", expand=True, fill="x", padx=Spacing.XS)
            attach_tooltip(btn, tip)
        return row

    # ------------------------------------------------------------------
    # Responsive
    # ------------------------------------------------------------------
    def set_compact(self, compact: bool) -> None:
        """Stack the two columns vertically when the window is narrow.

        The columns are CTkScrollableFrames: only their grid() is redirected
        to the visible outer frame (grid_configure() would move the inner one).
        """
        if compact:
            self.grid_columnconfigure((0, 1), weight=1, uniform="")
            self._left.grid(row=0, column=0, columnspan=2, sticky="nsew",
                            padx=Spacing.LG, pady=(Spacing.MD, Spacing.XS))
            self._right.grid(row=1, column=0, columnspan=2, sticky="nsew",
                             padx=Spacing.LG, pady=(Spacing.XS, Spacing.MD))
            self.grid_rowconfigure((0, 1), weight=1)
            self._actions.grid(row=2, column=0, columnspan=2, sticky="ew",
                               padx=Spacing.LG, pady=(0, Spacing.MD))
        else:
            self.grid_columnconfigure((0, 1), weight=1, uniform="cols")
            self._left.grid(row=0, column=0, columnspan=1, sticky="nsew",
                            padx=(Spacing.LG, Spacing.SM), pady=Spacing.MD)
            self._right.grid(row=0, column=1, columnspan=1, sticky="nsew",
                             padx=(Spacing.SM, Spacing.LG), pady=Spacing.MD)
            self.grid_rowconfigure(0, weight=1)
            self.grid_rowconfigure(1, weight=0)
            self._actions.grid(row=1, column=0, columnspan=2, sticky="ew",
                               padx=Spacing.LG, pady=(0, Spacing.MD))

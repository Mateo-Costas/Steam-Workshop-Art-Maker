"""ui.steps.step_file - step 1: pick the source file and inspect it."""
import customtkinter as ctk

from i18n import t
from ui import theme
from ui.theme import Colors, Spacing
from ui.widgets import attach_tooltip, darken


class FileStep(ctk.CTkFrame):
    """Drop zone, file picker and the metadata/preview panel.

    Exposes on the app (contract with ui.logic.files.FilesMixin):
        app.file_info_frame: container where show_file_info() renders.
    """

    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self._app = app

        # --- Drop zone -------------------------------------------------
        drop = ctk.CTkFrame(self, fg_color=Colors.BG_TERTIARY, corner_radius=12,
                            border_width=2, border_color=Colors.BORDER)
        drop.pack(fill="x", padx=Spacing.LG, pady=(Spacing.LG, Spacing.MD))

        ctk.CTkLabel(drop, text=t("drop_here", fallback="Arrastra tu archivo aqui"),
                     font=theme.font("HEADING"),
                     text_color=Colors.TEXT_SECONDARY).pack(pady=(Spacing.LG, Spacing.XS))
        ctk.CTkLabel(drop,
                     text=t("supported_formats",
                            fallback="MP4 · AVI · MOV · MKV · WEBM · GIF · JPG · PNG · WEBP"),
                     font=theme.font("CAPTION"),
                     text_color=Colors.TEXT_MUTED).pack()

        select_btn = ctk.CTkButton(
            drop, text=t("select_file_btn", fallback="Seleccionar archivo"),
            command=app.select_file,
            fg_color=Colors.ACCENT, hover_color=darken(Colors.ACCENT),
            height=theme.MIN_BUTTON_HEIGHT, corner_radius=8,
            font=theme.font("SMALL"))
        select_btn.pack(pady=(Spacing.MD, Spacing.LG))
        attach_tooltip(select_btn, t("tip_open_file",
                                     fallback="Abrir un archivo multimedia (Ctrl+O)"))

        # --- Content type: the user says whether it's anime -------------
        # A manual toggle replaced the CV auto-detection, which misclassified
        # too often; the choice drives the recommended AI model.
        options = ctk.CTkFrame(self, fg_color="transparent")
        options.pack(fill="x", padx=Spacing.LG)
        ctk.CTkLabel(options,
                     text=t("is_anime_question", fallback="¿Tu contenido es anime?"),
                     font=theme.font("SMALL"),
                     text_color=Colors.TEXT).pack(side="left")
        self._anime_yes = t("anime_yes", fallback="Sí, anime")
        self._anime_no = t("anime_no", fallback="No")
        selector = ctk.CTkSegmentedButton(
            options, values=[self._anime_yes, self._anime_no],
            command=self._on_anime_choice, font=theme.font("SMALL"),
            height=30, selected_color=Colors.ACCENT,
            selected_hover_color=darken(Colors.ACCENT))
        selector.set(self._anime_yes if app.config.get("ui.is_anime", True)
                     else self._anime_no)
        selector.pack(side="left", padx=(Spacing.MD, 0))
        attach_tooltip(selector, t(
            "tip_is_anime",
            fallback="Elige el tipo de contenido para recomendar el mejor modelo de IA"))

        # --- Recent files -----------------------------------------------
        self._recents_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._recents_frame.pack(fill="x", padx=Spacing.LG,
                                 pady=(Spacing.SM, 0))
        self.refresh_recents()

        # --- File info / preview (rendered by FilesMixin.show_file_info) ---
        app.file_info_frame = ctk.CTkFrame(self, fg_color="transparent")
        app.file_info_frame.pack(fill="both", expand=True,
                                 padx=Spacing.LG, pady=Spacing.MD)

    def refresh_recents(self) -> None:
        """Re-render the recent-files shortcut row."""
        for child in self._recents_frame.winfo_children():
            child.destroy()
        recents = self._app.get_recent_files()
        if not recents:
            return
        ctk.CTkLabel(self._recents_frame,
                     text=t("recent_files", fallback="Recientes:"),
                     font=theme.font("CAPTION"),
                     text_color=Colors.TEXT_MUTED).pack(side="left")
        for path in recents[:5]:
            btn = ctk.CTkButton(
                self._recents_frame, text=path.name, width=10,
                command=lambda p=path: self._open_recent(p),
                fg_color="transparent", border_width=1,
                border_color=Colors.BORDER, hover_color=Colors.HOVER,
                height=26, corner_radius=6, font=theme.font("CAPTION"),
                text_color=Colors.TEXT_SECONDARY)
            btn.pack(side="left", padx=(Spacing.XS, 0))
            attach_tooltip(btn, str(path))

    def _on_anime_choice(self, value: str) -> None:
        self._app.set_content_is_anime(value == self._anime_yes)

    def _open_recent(self, path) -> None:
        self._app.open_recent_file(path)
        self.refresh_recents()

    def set_compact(self, compact: bool) -> None:
        """Single-column layout already; nothing to reflow."""

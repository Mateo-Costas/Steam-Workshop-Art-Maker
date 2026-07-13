"""ui.steps.step_upload - step 4: get the generated fragments onto Steam."""
import os
import webbrowser

import customtkinter as ctk

from i18n import t
from ui import theme
from ui.theme import Colors, Spacing
from ui.widgets import attach_tooltip, darken

_WORKSHOP_UPLOAD_URL = "https://steamcommunity.com/sharedfiles/edititem/767/3/"

_MANUAL_STEPS = (
    "1. Abre la pagina de subida de Steam Workshop (boton de abajo).\n"
    "2. Abre la consola del navegador (F12 → Console).\n"
    "3. Pega el snippet JS (boton Copiar JS) y pulsa Enter.\n"
    "4. Sube cada fragmento, ponle titulo y guarda.\n"
    "5. Repite para cada pieza y ordenalas en tu perfil."
)


class UploadStep(ctk.CTkFrame):
    """Fragment list for the current file plus manual and automatic upload."""

    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self._app = app

        # --- Generated fragments ---------------------------------------
        self._list = ctk.CTkScrollableFrame(
            self, fg_color=Colors.BG_SECONDARY, corner_radius=10,
            label_text=t("fragments_ready", fallback="Fragmentos generados"),
            label_font=theme.font("SUBHEADING"))
        self._list.pack(fill="both", expand=True, padx=Spacing.LG,
                        pady=(Spacing.MD, Spacing.SM))

        refresh_btn = ctk.CTkButton(
            self, text=t("refresh_fragments", fallback="Actualizar lista"),
            command=self.refresh, width=160,
            fg_color="transparent", border_width=1, border_color=Colors.BORDER,
            hover_color=Colors.HOVER, height=30, corner_radius=6,
            font=theme.font("CAPTION"))
        refresh_btn.pack(anchor="e", padx=Spacing.LG)

        # --- Manual upload guide -----------------------------------------
        guide = ctk.CTkFrame(self, fg_color=Colors.BG_SECONDARY, corner_radius=10)
        guide.pack(fill="x", padx=Spacing.LG, pady=Spacing.SM)
        ctk.CTkLabel(guide, text=t("manual_upload", fallback="Subida manual"),
                     font=theme.font("SUBHEADING"),
                     text_color=Colors.TEXT).pack(anchor="w", padx=Spacing.SM,
                                                  pady=(Spacing.SM, 0))
        ctk.CTkLabel(guide, text=_MANUAL_STEPS, font=theme.font("CAPTION"),
                     text_color=Colors.TEXT_SECONDARY, justify="left").pack(
            anchor="w", padx=Spacing.SM, pady=(2, Spacing.SM))

        # --- Actions -----------------------------------------------------
        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.pack(fill="x", padx=Spacing.LG, pady=(0, Spacing.MD))

        buttons = (
            (t("open_fragments_folder", fallback="Abrir carpeta"),
             self._open_folder, Colors.BG_TERTIARY,
             t("tip_open_folder", fallback="Abrir la carpeta de fragmentos del archivo actual")),
            (t("copy_js", fallback="Copiar JS"),
             app._copy_steam_js, Colors.ACCENT,
             t("tip_copy_js", fallback="Copiar snippet para la consola del navegador")),
            (t("open_workshop", fallback="Abrir Workshop"),
             lambda: webbrowser.open(_WORKSHOP_UPLOAD_URL), Colors.BG_TERTIARY,
             t("tip_open_workshop", fallback="Abrir la pagina de subida de Steam")),
            (t("upload_tool", fallback="Upload Tool"),
             app._launch_upload_tool, "#16a34a",
             t("tip_upload_tool", fallback="Subida automatica")),
            (t("validate_profile", fallback="Validar perfil"),
             app.validate_steam_profile, "#8957e5",
             t("tip_validate_profile",
               fallback="Comprobar tu perfil Steam y nivel para showcases")),
            (t("export_zip", fallback="Export ZIP"),
             app.export_steam_pack, "#8957e5",
             t("tip_export_zip",
               fallback="Empaquetar fragmentos + instrucciones en un ZIP")),
        )
        for text, command, color, tip in buttons:
            btn = ctk.CTkButton(actions, text=text, command=command,
                                fg_color=color, hover_color=darken(color),
                                height=theme.MIN_BUTTON_HEIGHT, corner_radius=8,
                                font=theme.font("SMALL"))
            btn.pack(side="left", expand=True, fill="x", padx=Spacing.XS)
            attach_tooltip(btn, tip)

    # ------------------------------------------------------------------
    def refresh(self) -> None:
        """Re-list fragments in the current file's workspace."""
        for child in self._list.winfo_children():
            child.destroy()

        app = self._app
        if not app.current_file:
            self._hint(t("no_file_yet", fallback="Carga un archivo en el paso 1."))
            return

        fragments = []
        try:
            frag_dir = app.processor.get_fragments_dir(app.current_file)
            if frag_dir.exists():
                fragments = sorted(
                    p for p in frag_dir.iterdir()
                    if p.is_file() and p.suffix.lower() in
                    {".gif", ".jpg", ".jpeg", ".png"})
        except Exception:
            pass

        if not fragments:
            self._hint(t("no_fragments_yet",
                         fallback="Aun no hay fragmentos: usa el paso 3."))
            return
        for path in fragments:
            size_mb = path.stat().st_size / (1024 * 1024)
            mark = "✅" if size_mb <= 5.0 else "❌"
            ctk.CTkLabel(self._list,
                         text=f"{mark}  {path.name}  —  {size_mb:.2f} MB",
                         font=theme.font("MONO_SMALL"), anchor="w").pack(
                anchor="w", padx=Spacing.XS, pady=1)

    def _hint(self, text: str) -> None:
        ctk.CTkLabel(self._list, text=text, font=theme.font("SMALL"),
                     text_color=Colors.TEXT_MUTED).pack(pady=Spacing.MD)

    def _open_folder(self) -> None:
        app = self._app
        if not app.current_file:
            return
        try:
            frag_dir = app.processor.get_fragments_dir(app.current_file)
            if frag_dir.exists():
                os.startfile(str(frag_dir))
        except Exception:
            pass

    def set_compact(self, compact: bool) -> None:
        """Single-column layout already; nothing to reflow."""

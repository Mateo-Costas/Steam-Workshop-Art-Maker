"""ui.app - WorkshopArt main window: workflow stepper, log panel and status bar.

Layout (single column, top to bottom):
    header   - app title, language selector, font-scale selector, help
    stepper  - 1 Archivo · 2 Procesar · 3 Fragmentar · 4 Subir
    content  - the active step frame (all four are built once and raised)
    log      - collapsible process log (global, visible from any step)
    status   - progress bar, status text, system indicators, cancel button

All processing logic lives in ui.logic (GUIMethodsMixin); this module is
layout and wiring only. Worker threads never touch widgets directly - they
enqueue callables on self.update_queue (drained by update_ui_loop).
"""
import queue
import threading
from pathlib import Path
from tkinter import messagebox

import customtkinter as ctk
import tkinter as tk

from config import Config
from i18n import get_language, set_language, t
from processor import SteamProcessor
from theme_PRO import ModernThemePro
from ui import theme
from ui.logic import GUIMethodsMixin
from ui.steps import FileStep, FragmentStep, ProcessStep, UploadStep
from ui.theme import Colors, Spacing
from ui.widgets import StatusBar, Stepper, attach_tooltip, darken

# Optional subsystems - absent in the free build; stubs prevent AttributeErrors.
try:
    from quality_report import QualityReportSystem
    QUALITY_AVAILABLE = True
except ImportError:
    QUALITY_AVAILABLE = False

    class QualityReportSystem:  # type: ignore[no-redef]
        def __init__(self, *_a): ...
        def create_quality_report(self, *_a, **_kw): return None
        def show_quality_report_window(self, *_a): ...

try:
    from fragment_preview import FragmentPreviewSystem  # PRO-only feature
    PREVIEW_AVAILABLE = True
except ImportError:
    PREVIEW_AVAILABLE = False

    class FragmentPreviewSystem:  # type: ignore[no-redef]
        def __init__(self, *_a): ...
        def create_fragment_preview(self, *_a): ...

# windnd enables native Windows drag-and-drop; gracefully absent elsewhere.
try:
    import windnd
    WINDND_AVAILABLE = True
except ImportError:
    WINDND_AVAILABLE = False

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

#: Below this window width the two-column steps stack vertically.
_COMPACT_WIDTH = 1050

_SUPPORTED_DROP_EXTS = {'.mp4', '.avi', '.mov', '.mkv', '.webm', '.m4v', '.flv',
                        '.gif', '.jpg', '.jpeg', '.png', '.bmp', '.webp'}


class WorkshopArtGUI(GUIMethodsMixin):
    """Main application window. Processing methods come from GUIMethodsMixin."""

    def __init__(self):
        self.root = ctk.CTk()
        self.root.title("WorkshopArt v2.0")
        self.root.geometry("1150x760")
        self.root.minsize(900, 600)

        # --- Config, engine and auxiliary systems ---
        self.config = Config()
        theme.init_scale(self.config)
        self.processor = SteamProcessor(self.config)
        self.quality_reporter = QualityReportSystem(ModernThemePro.COLORS)
        self.fragment_previewer = FragmentPreviewSystem(ModernThemePro.COLORS)

        self.current_file = None
        self.content_analysis = None

        set_language(self.config.get("ui.language", "ES"))

        # --- Tkinter variables (contract with ui.logic mixins) ---
        self.progress_var = tk.DoubleVar()
        self.status_var = tk.StringVar(value=t("status_ready", fallback="Listo"))
        self.model_var = tk.StringVar()
        self.gpu_var = tk.BooleanVar(value=True)
        self.quality_var = tk.StringVar(value="Alta Calidad")
        self.contrast_var = tk.DoubleVar(value=1.5)
        self.saturation_var = tk.DoubleVar(value=1.3)
        self.vibrance_var = tk.DoubleVar(value=0.0)
        self.sharpness_var = tk.DoubleVar(value=0.0)
        self.temperature_var = tk.DoubleVar(value=0.0)
        self.enhance_colors_var = tk.BooleanVar(value=True)
        self.fps_60_var = tk.BooleanVar()
        self.auto_detect_var = tk.BooleanVar(value=True)

        self._cancel_event = threading.Event()
        self.update_queue = queue.Queue()
        self._compact = False

        self.setup_logging()
        self._build_ui()
        self._bind_shortcuts()
        self._setup_drag_and_drop()

        self.root.after(200, self.check_dependencies)
        self.root.after(500, self._refresh_step_state)
        self.root.bind("<Configure>", self._on_resize)
        self.update_ui_loop()

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        """Build (or rebuild, on language change) the full widget tree."""
        for child in self.root.winfo_children():
            child.destroy()

        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_rowconfigure(2, weight=1)

        self._build_header().grid(row=0, column=0, sticky="ew")
        self._stepper = Stepper(self.root, self._step_titles(), self._show_step)
        self._stepper.grid(row=1, column=0, sticky="ew",
                           padx=Spacing.LG, pady=(Spacing.SM, Spacing.XS))

        # Content: all steps live in the same grid cell; tkraise switches.
        content = ctk.CTkFrame(self.root, fg_color=Colors.BG_PRIMARY,
                               corner_radius=0)
        content.grid(row=2, column=0, sticky="nsew")
        content.grid_rowconfigure(0, weight=1)
        content.grid_columnconfigure(0, weight=1)
        self._steps = [
            FileStep(content, self),
            ProcessStep(content, self),
            FragmentStep(content, self, PREVIEW_AVAILABLE),
            UploadStep(content, self),
        ]
        for step in self._steps:
            step.grid(row=0, column=0, sticky="nsew")

        self._build_log_panel().grid(row=3, column=0, sticky="ew")

        status = StatusBar(self.root, self.status_var, self.progress_var,
                           self._on_cancel_processing)
        status.grid(row=4, column=0, sticky="ew")
        # Contract attributes used by SystemMixin.update_status/_system_status.
        self.status_icon = status.status_icon
        self.progress_bar = status.progress_bar
        self.gpu_status_label = status.gpu_status_label
        self.ffmpeg_status_label = status.ffmpeg_status_label
        self.models_status_label = status.models_status_label
        self._cancel_btn = status.cancel_btn

        self._steps[0].tkraise()

    def _build_header(self) -> ctk.CTkFrame:
        header = ctk.CTkFrame(self.root, fg_color=Colors.BG_SECONDARY,
                              corner_radius=0)
        ctk.CTkLabel(header, text="WorkshopArt", font=theme.font("TITLE"),
                     text_color=Colors.ACCENT).pack(side="left",
                                                    padx=(Spacing.LG, Spacing.XS))
        ctk.CTkLabel(header, text="v2.0", font=theme.font("CAPTION"),
                     text_color=Colors.TEXT_MUTED).pack(side="left", pady=(8, 0))

        help_btn = ctk.CTkButton(header, text=t("help", fallback="Ayuda"),
                                 command=self.show_help, width=90,
                                 fg_color="transparent", hover_color=Colors.HOVER,
                                 border_width=1, border_color=Colors.BORDER,
                                 height=30, corner_radius=6,
                                 font=theme.font("CAPTION"))
        help_btn.pack(side="right", padx=(Spacing.SM, Spacing.LG), pady=Spacing.SM)
        attach_tooltip(help_btn, t("tip_help", fallback="Guia completa (F1)"))

        scale = ctk.CTkOptionMenu(
            header, values=[f"{p}%" for p in theme.SCALE_OPTIONS],
            command=self._on_scale_change, width=84, height=30,
            font=theme.font("CAPTION"), fg_color=Colors.BG_TERTIARY,
            button_color=Colors.BG_TERTIARY, button_hover_color=Colors.HOVER)
        scale.set(f"{theme.get_scale_percent()}%")
        scale.pack(side="right", padx=Spacing.XS, pady=Spacing.SM)
        attach_tooltip(scale, t("tip_font_scale",
                                fallback="Tamano del texto (requiere reiniciar)"))

        lang = ctk.CTkSegmentedButton(
            header, values=["ES", "EN", "PT"], command=self._on_language_change,
            font=theme.font("CAPTION"), height=30,
            selected_color=Colors.ACCENT,
            selected_hover_color=darken(Colors.ACCENT))
        lang.set(get_language())
        lang.pack(side="right", padx=Spacing.XS, pady=Spacing.SM)
        return header

    def _build_log_panel(self) -> ctk.CTkFrame:
        panel = ctk.CTkFrame(self.root, fg_color=Colors.BG_PRIMARY,
                             corner_radius=0)
        bar = ctk.CTkFrame(panel, fg_color="transparent")
        bar.pack(fill="x", padx=Spacing.LG)
        self._log_toggle = ctk.CTkButton(
            bar, text="▸ " + t("log_title", fallback="Log de proceso"),
            command=self._toggle_log, width=180, anchor="w",
            fg_color="transparent", hover_color=Colors.HOVER, height=26,
            corner_radius=6, font=theme.font("CAPTION"),
            text_color=Colors.TEXT_MUTED)
        self._log_toggle.pack(side="left")

        self.process_log = ctk.CTkTextbox(
            panel, height=130, font=theme.font("MONO_SMALL"),
            fg_color=Colors.BG_SECONDARY, text_color=Colors.TEXT_SECONDARY,
            corner_radius=8, border_width=1, border_color=Colors.BORDER)
        self._log_visible = False  # collapsed by default; toggle to expand
        return panel

    @staticmethod
    def _step_titles() -> list:
        return [
            t("step_file", fallback="Archivo"),
            t("step_process", fallback="Procesar"),
            t("step_fragment", fallback="Fragmentar"),
            t("step_upload", fallback="Subir"),
        ]

    # ------------------------------------------------------------------
    # Navigation, responsive and state
    # ------------------------------------------------------------------
    def _show_step(self, index: int) -> None:
        self._steps[index].tkraise()
        if index == 1:
            self._steps[1].color_preview.refresh()
        elif index == 3:
            self._steps[3].refresh()

    def _refresh_step_state(self) -> None:
        """Enable steps 2-4 only when a file is loaded. Reschedules itself."""
        has_file = self.current_file is not None
        for index in (1, 2, 3):
            self._stepper.set_enabled(index, has_file)
        self.root.after(500, self._refresh_step_state)

    def _on_resize(self, event) -> None:
        if event.widget is not self.root:
            return
        compact = event.width < _COMPACT_WIDTH
        if compact != self._compact:
            self._compact = compact
            for step in self._steps:
                step.set_compact(compact)

    def _toggle_log(self) -> None:
        self._log_visible = not self._log_visible
        title = t("log_title", fallback="Log de proceso")
        if self._log_visible:
            self.process_log.pack(fill="x", padx=Spacing.LG,
                                  pady=(0, Spacing.SM))
            self._log_toggle.configure(text="▾ " + title)
        else:
            self.process_log.pack_forget()
            self._log_toggle.configure(text="▸ " + title)

    # ------------------------------------------------------------------
    # Header callbacks
    # ------------------------------------------------------------------
    def _on_language_change(self, lang: str) -> None:
        """Switch locale, persist it, and rebuild the widget tree."""
        set_language(lang)
        self.config.set("ui.language", lang)
        self._build_ui()
        if self.current_file:
            self.show_file_info()
        self.check_dependencies()

    def _on_scale_change(self, value: str) -> None:
        pct = int(value.rstrip("%"))
        self.config.set("ui.scale", pct)
        if pct != theme.get_scale_percent():
            messagebox.showinfo(
                t("font_scale", fallback="Tamano de texto"),
                t("restart_for_scale",
                  fallback="El nuevo tamano de texto se aplicara al reiniciar la aplicacion."))

    # ------------------------------------------------------------------
    # Cancel-button contract (used by ui.logic.system._run_cancellable)
    # ------------------------------------------------------------------
    def _on_cancel_processing(self) -> None:
        self._cancel_event.set()
        self._cancel_btn.pack_forget()
        self.status_var.set(t("cancelling", fallback="Cancelando..."))
        self.log_message(t("cancel_requested_log",
                           fallback="Cancelacion solicitada"), "WARNING")

    def _show_cancel_btn(self) -> None:
        self._cancel_event.clear()
        self._cancel_btn.pack(side="right", padx=Spacing.MD, pady=8)

    def _hide_cancel_btn(self) -> None:
        self._cancel_btn.pack_forget()

    # ------------------------------------------------------------------
    # Shortcuts and drag & drop
    # ------------------------------------------------------------------
    def _bind_shortcuts(self) -> None:
        self.root.bind("<Control-o>", lambda _e: self.select_file())
        self.root.bind("<F1>", lambda _e: self.show_help())
        for index in range(4):
            self.root.bind(f"<Control-Key-{index + 1}>",
                           lambda _e, i=index: self._stepper.select(i))

    def _setup_drag_and_drop(self) -> None:
        """Register the windnd drop hook (Windows only)."""
        if not WINDND_AVAILABLE:
            return

        def on_drop(files):
            for raw in files:
                path = Path(raw.decode() if isinstance(raw, bytes) else raw)
                if path.suffix.lower() in _SUPPORTED_DROP_EXTS:
                    self.current_file = path
                    self._stepper.select(0)
                    self.show_file_info()
                    if self.auto_detect_var.get():
                        self.analyze_content()
                    return
            messagebox.showwarning(
                t("unsupported_format_title", fallback="Formato no soportado"),
                t("unsupported_format_msg",
                  fallback="El archivo arrastrado no es un formato multimedia soportado."))

        windnd.hook_dropfiles(self.root, func=on_drop)

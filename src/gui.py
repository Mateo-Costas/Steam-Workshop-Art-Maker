"""
gui.py - Interfaz principal con CustomTkinter
Layout: sidebar izquierda | centro (drop + log) | panel derecho (config)
"""

import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
import threading
import queue
from pathlib import Path
from datetime import datetime
from PIL import Image, ImageTk
import matplotlib
matplotlib.use('Agg')

from config import Config
from theme_PRO import Colors, Fonts, ModernThemePro
from processor import SteamProcessor
from models import ModelManager
from analyzers import ContentAnalyzer
from gui_methods import GUIMethodsMixin
from i18n import t, set_language, get_language

try:
    from quality_report import QualityReportSystem
    QUALITY_AVAILABLE = True
except ImportError:
    QUALITY_AVAILABLE = False
    class QualityReportSystem:
        def create_quality_report(self, **kwargs): return None
        def show_quality_report_window(self, *args): pass

try:
    from fragment_preview import FragmentPreviewSystem
    PREVIEW_AVAILABLE = True
except ImportError:
    PREVIEW_AVAILABLE = False
    class FragmentPreviewSystem:
        def create_fragment_preview(self, *args): pass

try:
    import windnd
    WINDND_AVAILABLE = True
except ImportError:
    WINDND_AVAILABLE = False


# --- CustomTkinter global config ---
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class WorkshopArtGUI(GUIMethodsMixin):
    """Interfaz principal - minimalista y ordenada."""

    def __init__(self):
        self.root = ctk.CTk()
        self.root.title("WorkshopArt PRO v3.0")
        self.root.geometry("1150x750")
        self.root.minsize(960, 650)

        # --- Sistemas auxiliares ---
        try:
            self.quality_reporter = QualityReportSystem(ModernThemePro.COLORS)
        except Exception:
            class _Dummy:
                def create_quality_report(self, *a, **kw): return None
                def show_quality_report_window(self, *a): pass
            self.quality_reporter = _Dummy()

        try:
            self.fragment_previewer = FragmentPreviewSystem(ModernThemePro.COLORS)
        except Exception:
            class _Dummy2:
                def create_fragment_preview(self, *a): pass
            self.fragment_previewer = _Dummy2()

        # --- Config & processor ---
        self.config = Config()
        self.processor = SteamProcessor(self.config)
        self.current_file = None
        self.content_analysis = None

        # --- Load saved language ---
        saved_lang = self.config.get("ui.language", "ES")
        set_language(saved_lang)

        # --- Tkinter variables ---
        self.progress_var = tk.DoubleVar()
        self.status_var = tk.StringVar(value=t("status_ready"))
        self.model_var = tk.StringVar()
        self.gpu_var = tk.BooleanVar(value=True)
        self.quality_var = tk.StringVar(value="Alta Calidad")
        self.contrast_var = tk.DoubleVar(value=1.5)
        self.saturation_var = tk.DoubleVar(value=1.3)
        self.enhance_colors_var = tk.BooleanVar(value=True)
        self.fps_60_var = tk.BooleanVar()
        self.auto_detect_var = tk.BooleanVar(value=True)

        # --- Widget references for i18n refresh ---
        self._i18n_widgets = {}

        # --- Cancel event for processing ---
        self._cancel_event = threading.Event()

        # --- UI queue ---
        self.update_queue = queue.Queue()

        # --- Logging ---
        self.setup_logging()

        # --- Build UI ---
        self._build_layout()

        # --- Drag & drop ---
        self._setup_drag_and_drop()

        # --- Check deps after UI is ready ---
        self.root.after(200, self.check_dependencies)

        # --- UI loop ---
        self.update_ui_loop()

    # ------------------------------------------------------------------
    # Layout principal
    # ------------------------------------------------------------------
    def _build_layout(self):
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(1, weight=1)

        self._build_sidebar()
        self._build_center()
        self._build_right_panel()
        self._build_status_bar()

    # ------------------------------------------------------------------
    # Sidebar
    # ------------------------------------------------------------------
    def _build_sidebar(self):
        sidebar = ctk.CTkFrame(self.root, width=200, corner_radius=0,
                               fg_color=Colors.BG_SECONDARY)
        sidebar.grid(row=0, column=0, sticky="ns")
        sidebar.grid_propagate(False)

        # Logo / titulo
        ctk.CTkLabel(sidebar, text="WorkshopArt PRO",
                     font=("Segoe UI", 20, "bold"),
                     text_color=Colors.ACCENT).pack(pady=(25, 2))
        ctk.CTkLabel(sidebar, text="v3.0",
                     font=Fonts.CAPTION,
                     text_color=Colors.TEXT_MUTED).pack(pady=(0, 15))

        # Language selector
        lang_frame = ctk.CTkFrame(sidebar, fg_color="transparent")
        lang_frame.pack(fill="x", padx=15, pady=(0, 15))
        self._lang_selector = ctk.CTkSegmentedButton(
            lang_frame, values=["ES", "EN"],
            command=self._on_language_change,
            font=Fonts.CAPTION, height=28,
            selected_color=Colors.ACCENT,
            selected_hover_color=self._darken(Colors.ACCENT),
        )
        self._lang_selector.set(get_language())
        self._lang_selector.pack(fill="x")

        # Separador
        ctk.CTkFrame(sidebar, height=1, fg_color=Colors.BORDER).pack(
            fill="x", padx=20, pady=(0, 15))

        # Botones de accion con tooltips
        action_keys = [
            ("open_file",         self.select_file,         Colors.ACCENT),
            ("process_ai",        self.process_full_ai,     Colors.ACCENT_DARK),
            ("colors_only",       self.enhance_colors_only, Colors.SUCCESS),
            ("mp4_to_gif",        self.convert_mp4_to_gif,  Colors.WARNING),
            ("enhance_animation", self.enhance_animation,   Colors.WARNING),
            ("fragment_steam",    self.fragment_for_steam,   Colors.DANGER),
            ("fragment_showcase", self.fragment_for_showcase_preset, Colors.DANGER),
            ("optimize_size",     self.optimize_to_steam_limit, Colors.SUCCESS),
        ]

        self._sidebar_buttons = []
        for key, cmd, color in action_keys:
            btn = ctk.CTkButton(
                sidebar, text=t(key), command=cmd,
                fg_color=color, hover_color=self._darken(color),
                height=38, corner_radius=8,
                font=Fonts.SMALL,
            )
            btn.pack(fill="x", padx=15, pady=4)
            self.create_tooltip(btn, t(f"tip_{key}"))
            self._sidebar_buttons.append((btn, key))

        # Separador
        ctk.CTkFrame(sidebar, height=1, fg_color=Colors.BORDER).pack(
            fill="x", padx=20, pady=15)

        # Descargar modelos
        self._dl_btn = ctk.CTkButton(
            sidebar, text=t("download_models"), command=self.download_models,
            fg_color="transparent", border_width=1,
            border_color=Colors.BORDER, hover_color=Colors.HOVER,
            height=34, corner_radius=8, font=Fonts.SMALL,
        )
        self._dl_btn.pack(fill="x", padx=15, pady=4)
        self.create_tooltip(self._dl_btn, t("tip_download_models"))

        # Ayuda
        self._help_btn = ctk.CTkButton(
            sidebar, text=t("help"), command=self.show_help,
            fg_color="transparent", hover_color=Colors.HOVER,
            height=30, corner_radius=8, font=Fonts.CAPTION,
            text_color=Colors.TEXT_MUTED,
        )
        self._help_btn.pack(fill="x", padx=15, pady=(4, 0))

        # Spacer + status indicators al fondo
        sidebar.pack_propagate(False)
        bottom = ctk.CTkFrame(sidebar, fg_color="transparent")
        bottom.pack(side="bottom", fill="x", padx=15, pady=15)

        # Upload Tool button — always shown, inside bottom frame above status labels
        self._upload_tool_btn = ctk.CTkButton(
            bottom, text="🚀 Upload Tool",
            command=self._launch_upload_tool,
            fg_color="#16a34a", hover_color="#15803d",
            height=38, corner_radius=8, font=Fonts.SMALL,
        )
        self._upload_tool_btn.pack(fill="x", pady=(0, 8))

        ctk.CTkFrame(bottom, height=1, fg_color=Colors.BORDER).pack(
            fill="x", pady=(0, 8))

        self.gpu_status_label = ctk.CTkLabel(bottom, text=t("gpu_label"),
                                             font=Fonts.CAPTION,
                                             text_color=Colors.TEXT_MUTED)
        self.gpu_status_label.pack(anchor="w")
        self.ffmpeg_status_label = ctk.CTkLabel(bottom, text=t("ffmpeg_label"),
                                                font=Fonts.CAPTION,
                                                text_color=Colors.TEXT_MUTED)
        self.ffmpeg_status_label.pack(anchor="w")
        self.models_status_label = ctk.CTkLabel(bottom, text=t("models_label"),
                                                font=Fonts.CAPTION,
                                                text_color=Colors.TEXT_MUTED)
        self.models_status_label.pack(anchor="w")

    # ------------------------------------------------------------------
    # Centro: drop zone + log
    # ------------------------------------------------------------------
    def _build_center(self):
        center = ctk.CTkFrame(self.root, fg_color=Colors.BG_PRIMARY,
                              corner_radius=0)
        center.grid(row=0, column=1, sticky="nsew", padx=0, pady=0)
        center.grid_rowconfigure(1, weight=1)
        center.grid_columnconfigure(0, weight=1)

        # --- Drop zone ---
        drop_frame = ctk.CTkFrame(center, fg_color=Colors.BG_TERTIARY,
                                  corner_radius=12, height=160)
        drop_frame.grid(row=0, column=0, sticky="ew", padx=20, pady=(20, 10))
        drop_frame.grid_propagate(False)
        drop_frame.grid_rowconfigure(0, weight=1)
        drop_frame.grid_columnconfigure(0, weight=1)

        drop_inner = ctk.CTkFrame(drop_frame, fg_color="transparent")
        drop_inner.grid(row=0, column=0)

        self._drop_label = ctk.CTkLabel(drop_inner, text=t("drop_here"),
                     font=Fonts.HEADING,
                     text_color=Colors.TEXT_SECONDARY)
        self._drop_label.pack(pady=(10, 4))
        self._formats_label = ctk.CTkLabel(drop_inner, text=t("supported_formats"),
                     font=Fonts.CAPTION,
                     text_color=Colors.TEXT_MUTED)
        self._formats_label.pack()
        self._select_btn = ctk.CTkButton(drop_inner, text=t("select_file_btn"),
                      command=self.select_file,
                      fg_color=Colors.ACCENT, hover_color=Colors.ACCENT_DARK,
                      height=32, corner_radius=8,
                      font=Fonts.SMALL)
        self._select_btn.pack(pady=(12, 5))

        # File info
        self.file_info_frame = ctk.CTkFrame(center, fg_color="transparent")
        self.file_info_frame.grid(row=0, column=0, sticky="ew",
                                  padx=20, pady=(170, 0))

        # --- Log ---
        log_header = ctk.CTkFrame(center, fg_color="transparent")
        log_header.grid(row=1, column=0, sticky="new", padx=20, pady=(10, 0))
        self._log_title = ctk.CTkLabel(log_header, text=t("log_title"),
                     font=Fonts.HEADING,
                     text_color=Colors.TEXT)
        self._log_title.pack(anchor="w")

        self.process_log = ctk.CTkTextbox(
            center, font=Fonts.MONO_SMALL,
            fg_color=Colors.BG_SECONDARY,
            text_color=Colors.TEXT_SECONDARY,
            corner_radius=8,
            border_width=1, border_color=Colors.BORDER,
        )
        self.process_log.grid(row=1, column=0, sticky="nsew",
                              padx=20, pady=(35, 20))

    # ------------------------------------------------------------------
    # Panel derecho: configuracion
    # ------------------------------------------------------------------
    def _build_right_panel(self):
        panel = ctk.CTkScrollableFrame(
            self.root, width=260,
            fg_color=Colors.BG_SECONDARY,
            corner_radius=0,
            label_text=t("config_title"),
            label_font=Fonts.HEADING,
            label_text_color=Colors.TEXT,
        )
        panel.grid(row=0, column=2, sticky="ns")
        self._right_panel = panel

        # --- Modelo IA ---
        self._section_label(panel, t("ai_model"))
        self.model_combo = ctk.CTkComboBox(
            panel, variable=self.model_var,
            width=230, height=32,
            fg_color=Colors.BG_TERTIARY,
            border_color=Colors.BORDER,
            button_color=Colors.ACCENT,
            dropdown_fg_color=Colors.BG_ELEVATED,
            font=Fonts.SMALL,
            command=lambda _: self.update_model_info(),
        )
        self.model_combo.pack(fill="x", padx=10, pady=(0, 5))

        self.auto_detect_check = ctk.CTkCheckBox(
            panel, text=t("auto_detect_model"),
            variable=self.auto_detect_var,
            font=Fonts.SMALL,
            checkbox_width=18, checkbox_height=18,
        )
        self.auto_detect_check.pack(anchor="w", padx=10, pady=(0, 10))

        # --- GPU ---
        self._section_label(panel, t("processing_section"))
        self.gpu_switch = ctk.CTkSwitch(
            panel, text=t("use_gpu"),
            variable=self.gpu_var,
            font=Fonts.SMALL,
            progress_color=Colors.SUCCESS,
        )
        self.gpu_switch.pack(anchor="w", padx=10, pady=(0, 10))
        self.create_tooltip(self.gpu_switch, t("tip_use_gpu"))

        # --- Calidad ---
        self._section_label(panel, t("quality_section"))
        for val, key in [("Alta Calidad", "quality_high"), ("Balanceado", "quality_balanced")]:
            ctk.CTkRadioButton(
                panel, text=t(key), variable=self.quality_var, value=val,
                font=Fonts.SMALL,
                radiobutton_width=16, radiobutton_height=16,
            ).pack(anchor="w", padx=10, pady=2)

        # --- Mejoras ---
        self._section_label(panel, t("visual_enhancements"))
        ctk.CTkCheckBox(
            panel, text=t("enhance_colors"),
            variable=self.enhance_colors_var,
            font=Fonts.SMALL,
            checkbox_width=18, checkbox_height=18,
        ).pack(anchor="w", padx=10, pady=2)

        ctk.CTkCheckBox(
            panel, text=t("enhance_animation_check"),
            variable=self.fps_60_var,
            font=Fonts.SMALL,
            checkbox_width=18, checkbox_height=18,
        ).pack(anchor="w", padx=10, pady=(2, 10))

        # Contraste
        self._section_label(panel, t("contrast"))
        self.contrast_slider = ctk.CTkSlider(
            panel, from_=0.5, to=2.0, variable=self.contrast_var,
            width=220, height=16,
            progress_color=Colors.ACCENT,
            button_color=Colors.ACCENT,
        )
        self.contrast_slider.pack(padx=10, pady=(0, 2))
        self.contrast_value_label = ctk.CTkLabel(
            panel, text=f"{self.contrast_var.get():.1f}",
            font=Fonts.CAPTION, text_color=Colors.TEXT_MUTED)
        self.contrast_value_label.pack(anchor="e", padx=10)
        self.contrast_var.trace_add("write", self._on_contrast_change)

        # Saturacion
        self._section_label(panel, t("saturation"))
        self.saturation_slider = ctk.CTkSlider(
            panel, from_=0.5, to=2.0, variable=self.saturation_var,
            width=220, height=16,
            progress_color=Colors.ACCENT,
            button_color=Colors.ACCENT,
        )
        self.saturation_slider.pack(padx=10, pady=(0, 2))
        self.saturation_value_label = ctk.CTkLabel(
            panel, text=f"{self.saturation_var.get():.1f}",
            font=Fonts.CAPTION, text_color=Colors.TEXT_MUTED)
        self.saturation_value_label.pack(anchor="e", padx=10)
        self.saturation_var.trace_add("write", self._on_saturation_change)

        # --- Info modelo ---
        self._section_label(panel, t("model_info"))
        self.model_info_frame = ctk.CTkFrame(panel, fg_color="transparent")
        self.model_info_frame.pack(fill="x", padx=10, pady=(0, 10))

        # --- Steam Workshop quick ref ---
        self._section_label(panel, t("steam_workshop"))
        self._steam_info_label = ctk.CTkLabel(
            panel, text=t("steam_instructions"), font=Fonts.CAPTION,
            text_color=Colors.TEXT_MUTED,
            justify="left")
        self._steam_info_label.pack(anchor="w", padx=10, pady=(0, 5))
        self._tutorial_btn = ctk.CTkButton(
            panel, text=t("view_tutorial"),
            command=self.open_steam_tutorial,
            fg_color="transparent", hover_color=Colors.HOVER,
            height=28, corner_radius=6, font=Fonts.CAPTION,
            text_color=Colors.ACCENT,
            border_width=1, border_color=Colors.BORDER,
        )
        self._tutorial_btn.pack(fill="x", padx=10, pady=(0, 15))

        # --- Hardware requirements ---
        self._section_label(panel, t("hw_requirements"))
        self._hw_info_label = ctk.CTkLabel(
            panel, text=t("hw_info"), font=Fonts.CAPTION,
            text_color=Colors.TEXT_MUTED,
            justify="left", wraplength=230)
        self._hw_info_label.pack(anchor="w", padx=10, pady=(0, 15))

    # ------------------------------------------------------------------
    # Status bar
    # ------------------------------------------------------------------
    def _build_status_bar(self):
        bar = ctk.CTkFrame(self.root, height=40, corner_radius=0,
                           fg_color=Colors.BG_SECONDARY)
        bar.grid(row=1, column=0, columnspan=3, sticky="ew")

        self.progress_bar = ctk.CTkProgressBar(
            bar, variable=self.progress_var,
            width=300, height=6,
            progress_color=Colors.ACCENT,
            fg_color=Colors.BG_TERTIARY,
            corner_radius=3,
        )
        self.progress_bar.pack(side="left", padx=(15, 10), pady=10)
        self.progress_bar.set(0)

        self.status_icon = ctk.CTkLabel(bar, text="", font=("Segoe UI", 13),
                                        text_color=Colors.SUCCESS)
        self.status_icon.pack(side="left", padx=(0, 5))

        self.status_label = ctk.CTkLabel(bar, textvariable=self.status_var,
                                         font=Fonts.SMALL,
                                         text_color=Colors.TEXT_SECONDARY)
        self.status_label.pack(side="left")

        self._cancel_btn = ctk.CTkButton(
            bar, text=t("cancel_processing"), command=self._on_cancel_processing,
            fg_color=Colors.DANGER, hover_color=self._darken(Colors.DANGER),
            height=26, width=120, corner_radius=6, font=Fonts.CAPTION,
        )
        self._cancel_btn.pack(side="right", padx=15, pady=7)
        self._cancel_btn.pack_forget()  # Hidden by default

    # ------------------------------------------------------------------
    # Language change
    # ------------------------------------------------------------------
    def _on_language_change(self, lang):
        set_language(lang)
        self.config.set("ui.language", lang)
        self._refresh_ui_text()

    def _on_cancel_processing(self):
        """Signal all running processing threads to stop."""
        self._cancel_event.set()
        self._cancel_btn.pack_forget()
        self.status_var.set(t("cancelling"))
        self.log_message(t("cancel_requested_log"), "WARNING")

    def _show_cancel_btn(self):
        self._cancel_event.clear()
        self._cancel_btn.pack(side="right", padx=15, pady=7)

    def _hide_cancel_btn(self):
        self._cancel_btn.pack_forget()

    def _refresh_ui_text(self):
        """Refresh all visible text after language change."""
        # Sidebar buttons
        for btn, key in self._sidebar_buttons:
            btn.configure(text=t(key))
        self._dl_btn.configure(text=t("download_models"))
        self._help_btn.configure(text=t("help"))

        # Center
        self._drop_label.configure(text=t("drop_here"))
        self._formats_label.configure(text=t("supported_formats"))
        self._select_btn.configure(text=t("select_file_btn"))
        self._log_title.configure(text=t("log_title"))

        # Right panel
        self.auto_detect_check.configure(text=t("auto_detect_model"))
        self.gpu_switch.configure(text=t("use_gpu"))
        self._steam_info_label.configure(text=t("steam_instructions"))
        self._tutorial_btn.configure(text=t("view_tutorial"))
        self._hw_info_label.configure(text=t("hw_info"))

        # Status
        self.status_var.set(t("status_ready"))
        self._cancel_btn.configure(text=t("cancel_processing"))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _section_label(self, parent, text):
        ctk.CTkLabel(parent, text=text, font=("Segoe UI", 11, "bold"),
                     text_color=Colors.TEXT).pack(
            anchor="w", padx=10, pady=(12, 4))

    @staticmethod
    def _darken(hex_color, factor=0.8):
        h = hex_color.lstrip('#')
        r, g, b = (int(h[i:i+2], 16) for i in (0, 2, 4))
        return f'#{int(r*factor):02x}{int(g*factor):02x}{int(b*factor):02x}'

    def _on_contrast_change(self, *_):
        self.contrast_value_label.configure(
            text=f"{self.contrast_var.get():.1f}")

    def _on_saturation_change(self, *_):
        self.saturation_value_label.configure(
            text=f"{self.saturation_var.get():.1f}")

    def _setup_drag_and_drop(self):
        if not WINDND_AVAILABLE:
            return
        SUPPORTED = {'.mp4', '.avi', '.mov', '.mkv', '.webm', '.m4v', '.flv', '.gif',
                     '.jpg', '.jpeg', '.png', '.bmp', '.webp'}

        def on_drop(files):
            for raw in files:
                p = Path(raw.decode() if isinstance(raw, bytes) else raw)
                if p.suffix.lower() in SUPPORTED:
                    self.current_file = p
                    self.show_file_info()
                    if self.auto_detect_var.get():
                        self.analyze_content()
                    return
            messagebox.showwarning(t("unsupported_format_title"),
                                   t("unsupported_format_msg"))

        windnd.hook_dropfiles(self.root, func=on_drop)

    def _update_system_status_label(self, widget, text, ok):
        color = Colors.SUCCESS if ok else Colors.WARNING
        widget.configure(text=text, text_color=color)

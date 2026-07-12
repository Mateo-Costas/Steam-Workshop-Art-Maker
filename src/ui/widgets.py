"""ui.widgets - reusable CustomTkinter components for the WorkshopArt UI.

Each widget has one purpose and no knowledge of app state; the app and the
step frames compose them and wire the callbacks.
"""
from typing import Callable, Optional, Sequence

import customtkinter as ctk
import tkinter as tk

from ui import theme
from ui.theme import Colors, Spacing


def darken(hex_color: str, factor: float = 0.8) -> str:
    """Return ``hex_color`` darkened by ``factor`` (used for hover states)."""
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return f"#{int(r * factor):02x}{int(g * factor):02x}{int(b * factor):02x}"


def section_label(parent, text: str) -> ctk.CTkLabel:
    """Create and pack a bold section header label. Returns the label."""
    label = ctk.CTkLabel(parent, text=text, font=theme.font("SUBHEADING"),
                         text_color=Colors.TEXT)
    label.pack(anchor="w", padx=Spacing.SM, pady=(Spacing.MD, Spacing.XS))
    return label


def attach_tooltip(widget, text: str) -> None:
    """Attach a hover tooltip to ``widget``.

    Keeps a single Toplevel per widget (repeated <Enter> events reuse it)
    and always destroys it on <Leave>/<Destroy> so no orphan windows remain.
    """

    def on_enter(event):
        if getattr(widget, "_tooltip", None) is not None:
            return
        tip = tk.Toplevel(widget)
        tip.wm_overrideredirect(True)  # no title bar or window decorations
        tip.wm_geometry(f"+{event.x_root + 12}+{event.y_root + 12}")
        tk.Label(tip, text=text, bg=Colors.BG_ELEVATED, fg=Colors.TEXT,
                 font=theme.font("CAPTION"), padx=10, pady=5).pack()
        widget._tooltip = tip

    def on_leave(_event=None):
        tip = getattr(widget, "_tooltip", None)
        if tip is not None:
            try:
                tip.destroy()
            except tk.TclError:
                pass
            widget._tooltip = None

    widget.bind("<Enter>", on_enter, add="+")
    widget.bind("<Leave>", on_leave, add="+")
    widget.bind("<Destroy>", on_leave, add="+")


class Stepper(ctk.CTkFrame):
    """Horizontal 1..N step navigation bar.

    Unlike CTkTabview, step titles can be re-set at runtime (i18n) and steps
    can be enabled/disabled individually.

    Args:
        parent: Container widget.
        titles: One title per step, already translated.
        on_select: Called with the step index (0-based) when the user
            activates an enabled step.
    """

    def __init__(self, parent, titles: Sequence[str],
                 on_select: Callable[[int], None], **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self._on_select = on_select
        self._buttons: list[ctk.CTkButton] = []
        self._enabled: list[bool] = [True] * len(titles)
        self._active = 0

        for index, title in enumerate(titles):
            btn = ctk.CTkButton(
                self, text=f"{index + 1} · {title}",
                command=lambda i=index: self.select(i),
                height=theme.MIN_BUTTON_HEIGHT, corner_radius=8,
                font=theme.font("SMALL"),
                fg_color=Colors.BG_TERTIARY, hover_color=Colors.HOVER,
                text_color=Colors.TEXT_SECONDARY,
            )
            btn.pack(side="left", expand=True, fill="x",
                     padx=(0 if index == 0 else Spacing.XS, 0))
            self._buttons.append(btn)
        self._paint()

    def set_titles(self, titles: Sequence[str]) -> None:
        """Re-apply (translated) titles without rebuilding the bar."""
        for index, title in enumerate(titles):
            self._buttons[index].configure(text=f"{index + 1} · {title}")

    def set_enabled(self, index: int, enabled: bool) -> None:
        """Enable or disable one step button."""
        if self._enabled[index] == enabled:
            return
        self._enabled[index] = enabled
        self._buttons[index].configure(state="normal" if enabled else "disabled")
        self._paint()

    def select(self, index: int) -> None:
        """Activate a step (no-op when the step is disabled)."""
        if not self._enabled[index]:
            return
        self._active = index
        self._paint()
        self._on_select(index)

    @property
    def active(self) -> int:
        """Index of the currently active step."""
        return self._active

    def _paint(self) -> None:
        for index, btn in enumerate(self._buttons):
            if index == self._active:
                btn.configure(fg_color=Colors.ACCENT, text_color=Colors.BG_PRIMARY,
                              hover_color=darken(Colors.ACCENT))
            else:
                btn.configure(fg_color=Colors.BG_TERTIARY,
                              text_color=Colors.TEXT_SECONDARY if self._enabled[index]
                              else Colors.TEXT_MUTED,
                              hover_color=Colors.HOVER)


class SliderRow(ctk.CTkFrame):
    """Labelled slider with a live value readout.

    Args:
        parent: Container widget.
        label: Translated label text.
        variable: tk.DoubleVar bound to the slider.
        from_/to: Slider range.
        fmt: Format string for the value label (e.g. "{:.1f}", "{:+.2f}").
        color: Progress/knob color; defaults to the accent color.
    """

    def __init__(self, parent, label: str, variable: tk.DoubleVar,
                 from_: float, to: float, fmt: str = "{:.1f}",
                 color: Optional[str] = None, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        color = color or Colors.ACCENT
        self._fmt = fmt
        self._variable = variable

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x")
        ctk.CTkLabel(header, text=label, font=theme.font("SMALL"),
                     text_color=Colors.TEXT).pack(side="left")
        self._value_label = ctk.CTkLabel(header, text=fmt.format(variable.get()),
                                         font=theme.font("CAPTION"),
                                         text_color=Colors.TEXT_MUTED)
        self._value_label.pack(side="right")

        self.slider = ctk.CTkSlider(self, from_=from_, to=to, variable=variable,
                                    height=16, progress_color=color,
                                    button_color=color)
        self.slider.pack(fill="x", pady=(2, 0))
        variable.trace_add("write", self._on_change)

    def _on_change(self, *_args) -> None:
        try:
            self._value_label.configure(text=self._fmt.format(self._variable.get()))
        except tk.TclError:
            pass  # widget destroyed while a trace was still registered


class PresetCard(ctk.CTkFrame):
    """Selectable card describing one fragmentation preset.

    Args:
        parent: Container widget.
        key: Preset key stored in ``variable`` on selection.
        title: Human title of the preset.
        variable: Shared tk.StringVar for the radio group.
        dims: Dimensions line (accent color), optional.
        note: Explanatory line (muted), optional.
        badge: Small highlight tag (e.g. "MAS USADO"), optional.
    """

    def __init__(self, parent, key: str, title: str, variable: tk.StringVar,
                 dims: str = "", note: str = "", badge: str = "", **kwargs):
        super().__init__(parent, fg_color=Colors.BG_TERTIARY, corner_radius=8,
                         **kwargs)
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=Spacing.SM, pady=(Spacing.XS, 0))
        ctk.CTkRadioButton(row, text=title, variable=variable, value=key,
                           font=theme.font("SMALL")).pack(side="left", anchor="w")
        if badge:
            ctk.CTkLabel(row, text=badge, font=theme.font("CAPTION"),
                         text_color=Colors.ACCENT, fg_color=Colors.BG_PRIMARY,
                         corner_radius=4, padx=6, pady=1).pack(side="left",
                                                               padx=(Spacing.SM, 0))
        if dims:
            ctk.CTkLabel(self, text=dims, font=theme.font("CAPTION"),
                         text_color=Colors.ACCENT).pack(anchor="w", padx=28)
        if note:
            ctk.CTkLabel(self, text=note, font=theme.font("CAPTION"),
                         text_color=Colors.TEXT_MUTED, justify="left",
                         wraplength=560).pack(anchor="w", padx=28,
                                              pady=(0, Spacing.XS))


class StatusBar(ctk.CTkFrame):
    """Bottom status bar: progress, icon+message, system indicators, cancel.

    Exposes the exact attribute names the logic mixins expect:
    ``progress_bar``, ``status_icon``, ``status_label``, ``gpu_status_label``,
    ``ffmpeg_status_label``, ``models_status_label`` and ``cancel_btn``.
    """

    def __init__(self, parent, status_var: tk.StringVar,
                 progress_var: tk.DoubleVar, on_cancel: Callable[[], None],
                 **kwargs):
        super().__init__(parent, height=44, corner_radius=0,
                         fg_color=Colors.BG_SECONDARY, **kwargs)

        self.progress_bar = ctk.CTkProgressBar(
            self, variable=progress_var, width=240, height=6,
            progress_color=Colors.ACCENT, fg_color=Colors.BG_TERTIARY,
            corner_radius=3)
        self.progress_bar.pack(side="left", padx=(Spacing.MD, Spacing.SM), pady=10)
        self.progress_bar.set(0)

        self.status_icon = ctk.CTkLabel(self, text="", font=("Segoe UI", 13),
                                        text_color=Colors.SUCCESS)
        self.status_icon.pack(side="left", padx=(0, Spacing.XS))
        self.status_label = ctk.CTkLabel(self, textvariable=status_var,
                                         font=theme.font("SMALL"),
                                         text_color=Colors.TEXT_SECONDARY)
        self.status_label.pack(side="left")

        self.cancel_btn = ctk.CTkButton(
            self, text="Cancelar", command=on_cancel,
            fg_color=Colors.DANGER, hover_color=darken(Colors.DANGER),
            height=26, width=110, corner_radius=6, font=theme.font("CAPTION"))
        self.cancel_btn.pack(side="right", padx=Spacing.MD, pady=8)
        self.cancel_btn.pack_forget()  # hidden until a job is running

        # System indicators (right-aligned, populated by check_dependencies).
        indicators = ctk.CTkFrame(self, fg_color="transparent")
        indicators.pack(side="right", padx=Spacing.MD)
        self.gpu_status_label = self._indicator(indicators, "GPU: ...")
        self.ffmpeg_status_label = self._indicator(indicators, "FFmpeg: ...")
        self.models_status_label = self._indicator(indicators, "Modelos: ...")

    @staticmethod
    def _indicator(parent, text: str) -> ctk.CTkLabel:
        label = ctk.CTkLabel(parent, text=text, font=theme.font("CAPTION"),
                             text_color=Colors.TEXT_MUTED)
        label.pack(side="left", padx=(Spacing.SM, 0))
        return label

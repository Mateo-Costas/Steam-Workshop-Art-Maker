"""ui.color_preview - live preview of the color-adjustment sliders.

Shows one frame of the current file with contrast/saturation/vibrance/
sharpness/temperature applied, recomputed in a background thread with a
300 ms debounce so dragging a slider stays smooth. Supported sources:
static images and GIFs (videos would require a moviepy decode; a hint is
shown instead).
"""
import threading
from pathlib import Path
from typing import Optional

import customtkinter as ctk
from PIL import Image, ImageEnhance, ImageTk

from i18n import t
from ui import theme
from ui.theme import Colors, Spacing

_DEBOUNCE_MS = 300
_THUMB_SIZE = (300, 170)
_PREVIEWABLE_EXTS = {".gif", ".jpg", ".jpeg", ".png", ".bmp", ".webp"}


class ColorPreviewPanel(ctk.CTkFrame):
    """Live before/after thumbnail driven by the app's adjustment variables."""

    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self._app = app
        self._after_id: Optional[str] = None
        self._base_path: Optional[Path] = None
        self._base_frame: Optional[Image.Image] = None
        self._job = 0  # generation counter; stale worker results are dropped

        self._image_label = ctk.CTkLabel(
            self, text=t("preview_no_file",
                         fallback="Carga un GIF o imagen para ver el preview"),
            font=theme.font("CAPTION"), text_color=Colors.TEXT_MUTED,
            fg_color=Colors.BG_TERTIARY, corner_radius=8,
            width=_THUMB_SIZE[0], height=_THUMB_SIZE[1])
        self._image_label.pack(padx=Spacing.SM, pady=(0, Spacing.SM))

        for var in (app.contrast_var, app.saturation_var, app.vibrance_var,
                    app.sharpness_var, app.temperature_var):
            var.trace_add("write", self._schedule)

    # ------------------------------------------------------------------
    def refresh(self) -> None:
        """Recompute immediately (e.g. when the step becomes visible)."""
        self._schedule()

    def _schedule(self, *_args) -> None:
        if self._after_id is not None:
            try:
                self._app.root.after_cancel(self._after_id)
            except Exception:
                pass
        self._after_id = self._app.root.after(_DEBOUNCE_MS, self._start_render)

    def _start_render(self) -> None:
        self._after_id = None
        base = self._load_base_frame()
        if base is None:
            return
        self._job += 1
        job = self._job
        values = (self._app.contrast_var.get(), self._app.saturation_var.get(),
                  self._app.vibrance_var.get(), self._app.sharpness_var.get(),
                  self._app.temperature_var.get())
        threading.Thread(target=self._render_worker, args=(base, values, job),
                         daemon=True).start()

    def _load_base_frame(self) -> Optional[Image.Image]:
        """Return (and cache) the thumbnail-sized base frame for current_file."""
        path = self._app.current_file
        if not path or Path(path).suffix.lower() not in _PREVIEWABLE_EXTS:
            self._base_path = None
            self._base_frame = None
            self._show_hint()
            return None
        if path == self._base_path and self._base_frame is not None:
            return self._base_frame
        try:
            with Image.open(path) as img:
                frame = img.convert("RGB")
                frame.thumbnail(_THUMB_SIZE, Image.Resampling.LANCZOS)
                self._base_frame = frame.copy()
            self._base_path = path
            return self._base_frame
        except Exception:
            self._show_hint()
            return None

    def _render_worker(self, base: Image.Image, values: tuple, job: int) -> None:
        contrast, saturation, vibrance, sharpness, temperature = values
        frame = base.copy()
        try:
            if 0.5 <= contrast <= 3.0:
                frame = ImageEnhance.Contrast(frame).enhance(contrast)
            if 0.5 <= saturation <= 3.0:
                frame = ImageEnhance.Color(frame).enhance(saturation)
            proc = self._app.processor
            if vibrance > 0.01:
                frame = proc._apply_vibrance(frame, vibrance)
            if sharpness > 0.01:
                frame = proc._apply_sharpness(frame, sharpness)
            if abs(temperature) > 0.01:
                frame = proc._apply_temperature(frame, temperature)
        except Exception:
            return

        def install():
            if job != self._job or not self._image_label.winfo_exists():
                return
            photo = ImageTk.PhotoImage(frame)
            self._image_label.configure(image=photo, text="")
            self._image_label.image = photo  # keep a reference for tkinter

        self._app.update_queue.put((install, ()))

    def _show_hint(self) -> None:
        if self._image_label.winfo_exists():
            self._image_label.configure(
                image=None,
                text=t("preview_no_file",
                       fallback="Carga un GIF o imagen para ver el preview"))
            self._image_label.image = None

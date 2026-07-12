"""ui.color_preview - live, animated preview of the color-adjustment sliders.

Plays the current GIF (or shows the static image) with contrast/saturation/
vibrance/sharpness/temperature applied. Adjusted frames are recomputed in a
background thread with a 300 ms debounce so dragging a slider stays smooth;
the animation keeps looping with the previous frames until the new set is
ready. GIFs are sampled down to at most ``_MAX_PREVIEW_FRAMES`` frames so a
full re-render stays fast.
"""
import threading
from pathlib import Path
from typing import List, Optional

import customtkinter as ctk
from PIL import Image, ImageEnhance, ImageSequence, ImageTk

from i18n import t
from ui import theme
from ui.theme import Colors, Spacing

_DEBOUNCE_MS = 300
_THUMB_SIZE = (300, 170)
_MAX_PREVIEW_FRAMES = 20
_PREVIEWABLE_EXTS = {".gif", ".jpg", ".jpeg", ".png", ".bmp", ".webp"}


class ColorPreviewPanel(ctk.CTkFrame):
    """Animated thumbnail driven by the app's color-adjustment variables."""

    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self._app = app
        self._after_id: Optional[str] = None      # debounce timer
        self._anim_after_id: Optional[str] = None  # animation frame timer
        self._base_path: Optional[Path] = None
        self._base_frames: List[Image.Image] = []
        self._delay_ms = 100
        self._photos: List[ImageTk.PhotoImage] = []
        self._frame_index = 0
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
    # Scheduling
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
        frames = self._load_base_frames()
        if not frames:
            return
        self._job += 1
        values = (self._app.contrast_var.get(), self._app.saturation_var.get(),
                  self._app.vibrance_var.get(), self._app.sharpness_var.get(),
                  self._app.temperature_var.get())
        threading.Thread(target=self._render_worker,
                         args=(frames, values, self._job), daemon=True).start()

    # ------------------------------------------------------------------
    # Frame loading (cached per file)
    # ------------------------------------------------------------------
    def _load_base_frames(self) -> List[Image.Image]:
        """Return (and cache) sampled thumbnail frames for current_file."""
        path = self._app.current_file
        if not path or Path(path).suffix.lower() not in _PREVIEWABLE_EXTS:
            self._reset_to_hint()
            return []
        if path == self._base_path and self._base_frames:
            return self._base_frames
        try:
            frames: List[Image.Image] = []
            with Image.open(path) as img:
                total = getattr(img, "n_frames", 1)
                step = max(1, -(-total // _MAX_PREVIEW_FRAMES))  # ceil division
                self._delay_ms = max(30, int(img.info.get("duration", 100)) * step)
                for index, frame in enumerate(ImageSequence.Iterator(img)):
                    if index % step:
                        continue
                    thumb = frame.convert("RGB")
                    thumb.thumbnail(_THUMB_SIZE, Image.Resampling.LANCZOS)
                    frames.append(thumb.copy())
                    if len(frames) >= _MAX_PREVIEW_FRAMES:
                        break
            self._base_frames = frames
            self._base_path = path
            return frames
        except Exception:
            self._reset_to_hint()
            return []

    # ------------------------------------------------------------------
    # Rendering and animation
    # ------------------------------------------------------------------
    def _render_worker(self, frames: List[Image.Image], values: tuple,
                       job: int) -> None:
        contrast, saturation, vibrance, sharpness, temperature = values
        proc = self._app.processor
        adjusted: List[Image.Image] = []
        try:
            for base in frames:
                frame = base.copy()
                if 0.5 <= contrast <= 3.0:
                    frame = ImageEnhance.Contrast(frame).enhance(contrast)
                if 0.5 <= saturation <= 3.0:
                    frame = ImageEnhance.Color(frame).enhance(saturation)
                if vibrance > 0.01:
                    frame = proc._apply_vibrance(frame, vibrance)
                if sharpness > 0.01:
                    frame = proc._apply_sharpness(frame, sharpness)
                if abs(temperature) > 0.01:
                    frame = proc._apply_temperature(frame, temperature)
                adjusted.append(frame)
                if job != self._job:
                    return  # a newer slider value superseded this render
        except Exception:
            return

        def install():
            if job != self._job or not self._image_label.winfo_exists():
                return
            self._photos = [ImageTk.PhotoImage(f) for f in adjusted]
            self._frame_index = 0
            self._show_frame(0)
            self._restart_animation()

        self._app.update_queue.put((install, ()))

    def _restart_animation(self) -> None:
        self._stop_animation()
        if len(self._photos) > 1:
            self._anim_after_id = self._app.root.after(self._delay_ms,
                                                       self._advance_frame)

    def _advance_frame(self) -> None:
        self._anim_after_id = None
        if not self._photos or not self._image_label.winfo_exists():
            return
        self._frame_index = (self._frame_index + 1) % len(self._photos)
        self._show_frame(self._frame_index)
        self._anim_after_id = self._app.root.after(self._delay_ms,
                                                   self._advance_frame)

    def _show_frame(self, index: int) -> None:
        photo = self._photos[index]
        self._image_label.configure(image=photo, text="")
        self._image_label.image = photo  # keep a reference for tkinter

    def _stop_animation(self) -> None:
        if self._anim_after_id is not None:
            try:
                self._app.root.after_cancel(self._anim_after_id)
            except Exception:
                pass
            self._anim_after_id = None

    def _reset_to_hint(self) -> None:
        self._stop_animation()
        self._base_path = None
        self._base_frames = []
        self._photos = []
        if self._image_label.winfo_exists():
            self._image_label.configure(
                image=None,
                text=t("preview_no_file",
                       fallback="Carga un GIF o imagen para ver el preview"))
            self._image_label.image = None

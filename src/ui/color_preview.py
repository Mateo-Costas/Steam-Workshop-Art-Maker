"""ui.color_preview - live, animated preview of the color-adjustment sliders.

Plays the current GIF (or shows the static image) with contrast/saturation/
vibrance/sharpness/temperature applied. Frames are decoded and adjusted in a
background thread with a 300 ms debounce so dragging a slider stays smooth;
the animation keeps looping with the previous frames until the new set is
ready. GIFs are sampled down to at most ``_MAX_PREVIEW_FRAMES`` frames.
"""
import threading
from pathlib import Path
from typing import List, Optional

import customtkinter as ctk
from PIL import Image, ImageSequence, ImageTk

from gif_utils import open_image, read_timing
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
        self._after_id: Optional[str] = None       # debounce timer
        self._anim_after_id: Optional[str] = None  # animation frame timer
        self._cache_path: Optional[Path] = None
        self._cache_frames: List[Image.Image] = []
        self._delay_ms = 100
        self._photos: List[ImageTk.PhotoImage] = []
        self._frame_index = 0
        self._job = 0  # generation counter; stale worker results are dropped

        self._image_label = ctk.CTkLabel(
            self, text=t("preview_no_file", fallback="Carga un GIF o imagen para ver el preview"),
            font=theme.font("CAPTION"), text_color=Colors.TEXT_MUTED,
            fg_color=Colors.BG_TERTIARY, corner_radius=8,
            width=_THUMB_SIZE[0], height=_THUMB_SIZE[1], wraplength=_THUMB_SIZE[0] - 20)
        self._image_label.pack(padx=Spacing.SM, pady=(0, Spacing.SM))

        for var in (app.contrast_var, app.saturation_var, app.vibrance_var,
                    app.sharpness_var, app.temperature_var):
            var.trace_add("write", self._schedule)

    # ------------------------------------------------------------------
    # Scheduling
    # ------------------------------------------------------------------
    def refresh(self) -> None:
        """Recompute (e.g. when the step becomes visible)."""
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
        path = self._app.current_file
        if not path or Path(path).suffix.lower() not in _PREVIEWABLE_EXTS:
            self._reset_to_hint()
            return
        self._job += 1
        values = (self._app.contrast_var.get(), self._app.saturation_var.get(),
                  self._app.vibrance_var.get(), self._app.sharpness_var.get(),
                  self._app.temperature_var.get())
        threading.Thread(target=self._render_worker, args=(Path(path), values, self._job),
                         daemon=True).start()

    # ------------------------------------------------------------------
    # Worker: load (cached per file) + adjust
    # ------------------------------------------------------------------
    def _load_frames(self, path: Path) -> List[Image.Image]:
        if path == self._cache_path and self._cache_frames:
            return self._cache_frames
        frames: List[Image.Image] = []
        step = 1
        if path.suffix.lower() == ".gif":
            timing = read_timing(path)
            step = max(1, -(-timing.frames // _MAX_PREVIEW_FRAMES))  # ceil division
            sampled = max(1, -(-timing.frames // step))
            # Spread the real duration over the sampled frames: real speed.
            self._delay_ms = max(20, timing.duration_ms // sampled)
        with open_image(path) as img:
            for index, frame in enumerate(ImageSequence.Iterator(img)):
                if index % step:
                    continue
                thumb = frame.convert("RGB")
                thumb.thumbnail(_THUMB_SIZE, Image.Resampling.LANCZOS)
                frames.append(thumb)
                if len(frames) >= _MAX_PREVIEW_FRAMES:
                    break
        self._cache_path, self._cache_frames = path, frames
        return frames

    def _render_worker(self, path: Path, values: tuple, job: int) -> None:
        contrast, saturation, vibrance, sharpness, temperature = values
        processor = self._app.processor
        try:
            frames = self._load_frames(path)
            adjusted = []
            for frame in frames:
                if job != self._job:
                    return  # a newer slider value superseded this render
                adjusted.append(processor.apply_color_adjustments(
                    frame, contrast, saturation, vibrance, sharpness, temperature))
        except Exception:
            self._app.update_queue.put((self._reset_to_hint, ()))
            return

        def install():
            if job != self._job or not self._image_label.winfo_exists():
                return
            self._photos = [ImageTk.PhotoImage(f) for f in adjusted]
            self._frame_index = 0
            self._show_frame(0)
            self._restart_animation()

        self._app.update_queue.put((install, ()))

    # ------------------------------------------------------------------
    # Animation
    # ------------------------------------------------------------------
    def _restart_animation(self) -> None:
        self._stop_animation()
        if len(self._photos) > 1:
            self._anim_after_id = self._app.root.after(self._delay_ms, self._advance_frame)

    def _advance_frame(self) -> None:
        self._anim_after_id = None
        if not self._photos or not self._image_label.winfo_exists():
            return
        self._frame_index = (self._frame_index + 1) % len(self._photos)
        self._show_frame(self._frame_index)
        self._anim_after_id = self._app.root.after(self._delay_ms, self._advance_frame)

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
        self._photos = []
        if self._image_label.winfo_exists():
            self._image_label.configure(
                image="", text=t("preview_no_file", fallback="Carga un GIF o imagen para ver el preview"))
            self._image_label.image = None

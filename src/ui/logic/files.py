"""ui.logic.files - file selection, metadata panel and animated previews."""
import threading
from pathlib import Path

import customtkinter as ctk
from PIL import Image, ImageSequence, ImageTk
from tkinter import filedialog

from gif_utils import open_gif, read_timing
from i18n import t
from ui import theme
from ui.logic.common import IMAGE_EXTS, MEDIA_EXTS, VIDEO_EXTS, steam_format_suggestion
from ui.theme import Colors
from video_utils import probe_video, sample_frames

_THUMB = (375, 250)
#: Frames kept in memory for the step-1 preview (GIF and video).
_PREVIEW_MAX_FRAMES = 240


class FilesMixin:
    """File picking, metadata display and GIF/video preview playback."""

    #: Maximum number of entries kept in the recent-files list.
    _MAX_RECENT_FILES = 8

    # ------------------------------------------------------------------
    # Picking files
    # ------------------------------------------------------------------
    def _remember_recent(self, path: Path) -> None:
        """Prepend ``path`` to the persisted recent-files list (deduplicated)."""
        recent = [str(path)] + [p for p in self.config.get("ui.recent_files", [])
                                if p != str(path)]
        self.config.set("ui.recent_files", recent[: self._MAX_RECENT_FILES])

    def get_recent_files(self) -> list:
        """Recent files that still exist on disk, most recent first."""
        return [Path(p) for p in self.config.get("ui.recent_files", []) if Path(p).exists()]

    def open_recent_file(self, path: Path) -> None:
        """Load a file from the recents list as if it had been picked."""
        if not path.exists():
            self._ui_warn(t("not_found", fallback="No encontrado"),
                          t("file_missing", fallback="El archivo ya no existe:\n{path}", path=path))
            return
        self.load_file(path)

    def select_file(self):
        """Open the file picker and load the chosen media file."""
        patterns = " ".join(f"*{ext}" for ext in sorted(MEDIA_EXTS))
        filename = filedialog.askopenfilename(
            parent=self.root,
            title=t("select_file_btn", fallback="Seleccionar archivo"),
            filetypes=[
                (t("media_files", fallback="Archivos multimedia"), patterns),
                ("GIF", "*.gif"),
                (t("videos", fallback="Videos"), " ".join(f"*{e}" for e in sorted(VIDEO_EXTS))),
                (t("images", fallback="Imágenes"), " ".join(f"*{e}" for e in sorted(IMAGE_EXTS))),
                (t("all_files", fallback="Todos"), "*.*"),
            ])
        if filename:
            self.load_file(Path(filename))

    def load_file(self, path: Path) -> None:
        """Make ``path`` the current file and refresh everything that depends on it."""
        self.current_file = Path(path)
        self.show_file_info()
        try:
            self._steps[0].refresh_recents()
        except (AttributeError, IndexError):
            pass

    # ------------------------------------------------------------------
    # Preview animation
    # ------------------------------------------------------------------
    def _stop_gif_animation(self):
        """Cancel the preview animation loop and drop its frames."""
        if getattr(self, "_gif_after_id", None):
            try:
                self.root.after_cancel(self._gif_after_id)
            except Exception:
                pass
        self._gif_after_id = None
        self._gif_frames = []
        self._gif_frame_index = 0

    def _animate_gif(self, label):
        """Show the next preview frame and reschedule (main thread only)."""
        frames = self._gif_frames
        if not frames or not label.winfo_exists():
            return
        self._gif_frame_index = (self._gif_frame_index + 1) % len(frames)
        photo = frames[self._gif_frame_index]
        label.configure(image=photo)
        label.image = photo  # keep a reference for tkinter
        self._gif_after_id = self.root.after(self._gif_frame_delay, self._animate_gif, label)

    def _start_preview(self, preview_frame, loader):
        """Decode preview frames in a thread with ``loader() -> (frames, delay_ms)``,
        then install the animation on the main thread."""
        source = self.current_file
        placeholder = ctk.CTkLabel(preview_frame, text=t("loading_preview", fallback="Cargando preview..."),
                                   width=_THUMB[0], height=_THUMB[1] // 2)
        placeholder.pack()

        def worker():
            try:
                frames, delay_ms = loader()
            except Exception as e:
                self.log_message(f"Preview no disponible: {e}", "WARNING")
                frames, delay_ms = [], 100

            def install():
                if self.current_file != source or not placeholder.winfo_exists():
                    return  # the user picked another file meanwhile
                if not frames:
                    placeholder.configure(text=t("preview_unavailable", fallback="(preview no disponible)"))
                    return
                self._stop_gif_animation()
                self._gif_frames = [ImageTk.PhotoImage(f) for f in frames]
                self._gif_frame_delay = max(20, int(delay_ms))
                placeholder.destroy()
                label = ctk.CTkLabel(preview_frame, text="", image=self._gif_frames[0])
                label.image = self._gif_frames[0]
                label.pack()
                if len(self._gif_frames) > 1:
                    self._gif_after_id = self.root.after(self._gif_frame_delay,
                                                         self._animate_gif, label)

            self.update_queue.put((install, ()))

        threading.Thread(target=worker, daemon=True).start()

    def _load_gif_preview(self, path: Path):
        """Up to _PREVIEW_MAX_FRAMES thumbnails spread over the whole GIF."""
        timing = read_timing(path)
        step = max(1, -(-timing.frames // _PREVIEW_MAX_FRAMES))  # ceil division
        frames, current = [], self.current_file
        with open_gif(path) as gif:
            for index, frame in enumerate(ImageSequence.Iterator(gif)):
                if index % step:
                    continue
                if self.current_file != current:
                    return [], 100
                thumb = frame.convert("RGBA")
                thumb.thumbnail(_THUMB, Image.Resampling.LANCZOS)
                frames.append(thumb)
        delays = timing.effective_delays or [100]
        return frames, sum(delays) / max(1, len(frames))

    # ------------------------------------------------------------------
    # File info panel
    # ------------------------------------------------------------------
    def show_file_info(self):
        """Render the preview and the metadata of the current file."""
        if not self.current_file:
            return
        path = self.current_file
        self._remember_recent(path)
        self._stop_gif_animation()
        for widget in self.file_info_frame.winfo_children():
            widget.destroy()

        content = ctk.CTkFrame(self.file_info_frame, fg_color="transparent")
        content.pack(fill="x")
        preview_frame = ctk.CTkFrame(content, fg_color="transparent")
        preview_frame.pack(side="left", padx=(0, 15))
        info_frame = ctk.CTkFrame(content, fg_color="transparent")
        info_frame.pack(side="left", fill="both", expand=True)

        ext = path.suffix.lower()
        details = [t("info_size", fallback="Tamaño: {mb:.2f} MB", mb=path.stat().st_size / 1048576)]
        width = height = 0
        try:
            if ext == ".gif":
                timing = read_timing(path)
                width, height = timing.width, timing.height
                fps = timing.frames * 1000 / max(1, timing.duration_ms)
                details += [t("info_dims", fallback="Dimensiones: {w}x{h}", w=width, h=height),
                            t("info_frames", fallback="Frames: {n}", n=timing.frames),
                            t("info_duration", fallback="Duración: {s:.1f} s", s=timing.duration_ms / 1000),
                            f"FPS: {fps:.1f}"]
                self._start_preview(preview_frame, lambda: self._load_gif_preview(path))
            elif ext in VIDEO_EXTS:
                info = probe_video(path)
                width, height = info.width, info.height
                details += [t("info_dims", fallback="Dimensiones: {w}x{h}", w=width, h=height),
                            t("info_duration", fallback="Duración: {s:.1f} s", s=info.duration),
                            f"FPS: {info.fps:.1f}"]
                self._start_preview(preview_frame, lambda: sample_frames(
                    path, _PREVIEW_MAX_FRAMES, _THUMB, lambda: self.current_file != path))
            elif ext in IMAGE_EXTS:
                with Image.open(path) as img:
                    width, height = img.size
                    thumb = img.convert("RGBA")
                thumb.thumbnail(_THUMB, Image.Resampling.LANCZOS)
                photo = ImageTk.PhotoImage(thumb)
                label = ctk.CTkLabel(preview_frame, text="", image=photo)
                label.image = photo
                label.pack()
                details.append(t("info_dims", fallback="Dimensiones: {w}x{h}", w=width, h=height))
        except Exception as e:
            details.append(t("info_unreadable", fallback="No se pudo leer el archivo: {err}", err=e))
            self.log_message(f"No se pudo leer {path.name}: {e}", "WARNING")

        suggestion = steam_format_suggestion(width, height)
        if suggestion:
            details.append(t("info_suggested", fallback="Formato sugerido: {preset}", preset=suggestion))

        ctk.CTkLabel(info_frame, text=path.name, font=theme.font("SUBHEADING"),
                     text_color=Colors.TEXT, wraplength=420, justify="left").pack(anchor="w")
        ctk.CTkLabel(info_frame, text="\n".join(details), font=theme.font("CAPTION"),
                     text_color=Colors.TEXT_SECONDARY, justify="left").pack(anchor="w", pady=(5, 0))

        self.log_message(f"Archivo cargado: {path.name}")
        self.update_status(t("status_file_loaded", fallback="Archivo cargado"), 100, "✅")

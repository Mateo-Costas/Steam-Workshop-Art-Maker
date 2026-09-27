"""
fragment_preview.py - preview of how a file will be cut into a showcase preset.

The geometry comes from SteamProcessor.preset_config, and the frame is
filled and center-cropped exactly like the real fragmentation, so what you
see is what the fragments will contain. It is drawn on a neutral background:
no attempt to mimic the Steam profile page (its layout changes over time).

Optional "profile" mode fetches your Steam name and avatar from the public
Community XML endpoint (no API key) and shows them above the preview.
"""

import io
import logging
import os
import threading
import tkinter as tk
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageSequence, ImageTk

from gif_utils import open_gif, read_timing
from i18n import t
from video_utils import IMAGE_EXTS, is_video, sample_frames

logger = logging.getLogger("WorkshopArt.fragment_preview")

_BG = (18, 24, 32)          # canvas background
_BAR = (28, 38, 52)         # header bar
_TEXT = (200, 212, 224)
_MUTED = (128, 143, 156)
_PAD = 18
_GAP = 4                    # gap between fragments, like the profile grid
_MAX_W = 700                # preview width available for the fragments
_MAX_H = 520                # height cap (tall free-height presets are scaled down)
_BAR_H = 40
_AVATAR = 24
_MAX_FRAMES = 60            # frames kept for the animated preview
_LOAD_WIDTH = 1000          # source frames are shrunk to this width on load


class _ProfileFetcher:
    """Public Steam profile data via the Community XML endpoint (no API key)."""

    _HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    }

    def fetch(self, profile_url: str, status_cb: Callable[[str], None]) -> dict:
        """Return {'name': str, 'avatar': PIL image or None, 'online': bool}."""
        base = profile_url.rstrip("/")
        xml_url = base if "?xml=1" in base else base + "/?xml=1"
        status_cb(t("profile_checking", fallback="Consultando Steam..."))
        try:
            request = urllib.request.Request(xml_url, headers=self._HEADERS)
            with urllib.request.urlopen(request, timeout=12) as response:
                raw = response.read()
        except OSError as exc:
            raise RuntimeError(t("steam_unreachable", fallback="No se pudo conectar con Steam: {err}",
                                 err=exc)) from exc
        try:
            root = ET.fromstring(raw)
        except ET.ParseError as exc:
            raise RuntimeError(t("steam_bad_answer",
                                 fallback="Respuesta inesperada de Steam (¿perfil privado?)")) from exc
        error = root.findtext("error")
        if error:
            raise RuntimeError(t("profile_unavailable", fallback="Perfil no disponible: {err}", err=error))

        name = root.findtext("steamID") or "SteamUser"
        avatar_url = root.findtext("avatarFull") or root.findtext("avatarMedium") or ""
        online = (root.findtext("onlineState") or "").lower() in ("online", "in-game")
        avatar = None
        if avatar_url:
            try:
                request = urllib.request.Request(avatar_url, headers=self._HEADERS)
                with urllib.request.urlopen(request, timeout=10) as response:
                    avatar = Image.open(io.BytesIO(response.read())).convert("RGB")
            except OSError:
                pass  # the avatar is optional
        return {"name": name, "avatar": avatar, "online": online}


def _font(size: int, bold: bool = False):
    fonts = os.path.join(os.environ.get("SystemRoot", "C:\\Windows"), "Fonts")
    for name in (("segoeuib.ttf" if bold else "segoeui.ttf"), "arial.ttf"):
        try:
            return ImageFont.truetype(os.path.join(fonts, name), size)
        except OSError:
            continue
    return ImageFont.load_default()


class _Layout:
    """Display geometry of one preset for a given source size."""

    def __init__(self, cfg: dict, source_size: Tuple[int, int]):
        total_w = cfg["total_w"]
        src_w, src_h = source_size
        canvas_h = cfg["fixed_h"] or max(2, 2 * round(src_h * total_w / max(1, src_w) / 2))
        count = len(cfg["parts"])
        scale = min((_MAX_W - _GAP * (count - 1)) / total_w, _MAX_H / canvas_h)
        self.canvas = (max(1, round(total_w * scale)), max(1, round(canvas_h * scale)))
        self.parts = [(round(left * scale), max(1, round(w * scale))) for _n, w, left in cfg["parts"]]
        self.width = sum(w for _l, w in self.parts) + _GAP * (count - 1) + 2 * _PAD
        self.height = _BAR_H + self.canvas[1] + 2 * _PAD

    def compose(self, frame: Image.Image, background: Image.Image) -> Image.Image:
        """Fill-and-crop the frame to the canvas (like FFmpeg), cut it into parts, lay them out."""
        canvas = ImageOps.fit(frame.convert("RGB"), self.canvas, Image.Resampling.LANCZOS)
        out = background.copy()
        x = _PAD
        for left, width in self.parts:
            out.paste(canvas.crop((left, 0, left + width, self.canvas[1])), (x, _BAR_H + _PAD))
            x += width + _GAP
        return out


class FragmentPreviewSystem:
    """Opens the fragment preview window."""

    def __init__(self, processor):
        self._processor = processor
        self._photos: List[ImageTk.PhotoImage] = []

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------
    @staticmethod
    def _load_frames(path: Path) -> Tuple[List[Image.Image], int]:
        """(RGB frames spread over the whole file, delay between them in ms)."""
        path = Path(path)
        if path.suffix.lower() in IMAGE_EXTS:
            with Image.open(path) as img:
                return [img.convert("RGB")], 100
        if is_video(path):
            frames, delay = sample_frames(path, _MAX_FRAMES, (_LOAD_WIDTH, _LOAD_WIDTH))
            return [f.convert("RGB") for f in frames], delay
        timing = read_timing(path)
        step = max(1, -(-timing.frames // _MAX_FRAMES))
        frames = []
        with open_gif(path) as gif:
            for index, frame in enumerate(ImageSequence.Iterator(gif)):
                if index % step == 0:
                    rgb = frame.convert("RGB")
                    rgb.thumbnail((_LOAD_WIDTH, _LOAD_WIDTH), Image.Resampling.LANCZOS)
                    frames.append(rgb)
        delay = max(20, timing.duration_ms // max(1, len(frames)))
        return frames, delay

    # ------------------------------------------------------------------
    # Window
    # ------------------------------------------------------------------
    def create_fragment_preview(self, source: Path, parent_window, preset: Optional[str] = None):
        presets = list(self._processor.SHOWCASE_PRESETS)
        preset = preset if preset in presets else "workshop_5part"
        try:
            frames, delay = self._load_frames(source)
        except Exception as e:
            raise RuntimeError(t("preview_load_failed", fallback="No se pudo cargar {file}: {err}",
                                 file=Path(source).name, err=e)) from e
        if not frames:
            raise RuntimeError(t("preview_load_failed", fallback="No se pudo cargar {file}: {err}",
                                 file=Path(source).name, err="0 frames"))

        win = tk.Toplevel(parent_window)
        win.title(t("open_preview", fallback="Preview de fragmentos") + " - WorkshopArt")
        win.resizable(False, False)
        win.configure(bg="#0e1921")
        win.transient(parent_window)
        win.after(50, win.grab_set)

        bar = tk.Frame(win, bg="#0e1921")
        bar.pack(fill="x", side="top")
        titles = {key: t(f"preset_{key}", fallback=self._processor.SHOWCASE_PRESETS[key]["desc"])
                  for key in presets}
        key_by_title = {title: key for key, title in titles.items()}
        preset_var = tk.StringVar(value=titles[preset])
        tk.Label(bar, text=t("preset_label", fallback="Preset:"), bg="#0e1921", fg="#7b8a97",
                 font=("Segoe UI", 9)).pack(side="left", padx=(10, 4), pady=6)
        menu = tk.OptionMenu(bar, preset_var, *titles.values(), command=lambda _v: render())
        menu.configure(bg="#2a475e", fg="#c6d4df", activebackground="#1b2838",
                       highlightthickness=0, relief="flat", font=("Segoe UI", 9))
        menu["menu"].configure(bg="#2a475e", fg="#c6d4df", font=("Segoe UI", 9))
        menu.pack(side="left", pady=6)

        profile = {"name": None, "avatar": None}
        url_var = tk.StringVar(value="")
        tk.Label(bar, text=t("profile_short", fallback="Tu perfil:"), bg="#0e1921", fg="#7b8a97",
                 font=("Segoe UI", 9)).pack(side="left", padx=(14, 4))
        tk.Entry(bar, textvariable=url_var, width=28, bg="#2a475e", fg="#c6d4df",
                 insertbackground="#c6d4df", relief="flat").pack(side="left", padx=(0, 4), ipady=3)
        status = tk.Label(bar, text="", bg="#0e1921", fg="#66c0f4", font=("Segoe UI", 9))

        def load_profile():
            url = url_var.get().strip()
            if not url:
                return
            if not url.startswith("http"):
                url = f"https://steamcommunity.com/id/{url}"

            def task():
                try:
                    data = _ProfileFetcher().fetch(url, lambda m: win.after(0, status.config, {"text": m}))
                    profile.update(name=data["name"], avatar=data["avatar"])
                    win.after(0, render)
                    win.after(0, status.config, {"text": ""})
                except Exception as exc:
                    win.after(0, status.config, {"text": str(exc)})

            threading.Thread(target=task, daemon=True).start()

        tk.Button(bar, text=t("show_my_profile", fallback="Mostrar mi perfil"), command=load_profile,
                  bg="#1b2838", fg="#c6d4df", relief="flat", font=("Segoe UI", 9),
                  padx=8).pack(side="left")
        status.pack(side="left", padx=8)

        canvas = tk.Canvas(win, bg="#1b2838", highlightthickness=0)
        canvas.pack(side="top")
        anim = {"after": None, "index": 0, "frames": []}

        def stop():
            if anim["after"]:
                win.after_cancel(anim["after"])
                anim["after"] = None

        def render():
            stop()
            key = key_by_title.get(preset_var.get(), preset)
            layout = _Layout(self._processor.preset_config(key), frames[0].size)
            background = self._background(layout, titles[key], profile)
            composed = [layout.compose(frame, background) for frame in frames]
            anim["frames"] = [ImageTk.PhotoImage(img) for img in composed]
            anim["index"] = 0
            canvas.configure(width=layout.width, height=layout.height)
            tick()

        def tick():
            photos = anim["frames"]
            if not photos or not canvas.winfo_exists():
                return
            photo = photos[anim["index"] % len(photos)]
            canvas.delete("all")
            canvas.create_image(0, 0, image=photo, anchor="nw")
            self._photos = photos  # keep references alive
            anim["index"] += 1
            if len(photos) > 1:
                anim["after"] = win.after(delay, tick)

        win.protocol("WM_DELETE_WINDOW", lambda: (stop(), win.destroy()))
        win.after(30, render)

    @staticmethod
    def _background(layout: "_Layout", title: str, profile: dict) -> Image.Image:
        img = Image.new("RGB", (layout.width, layout.height), _BG)
        draw = ImageDraw.Draw(img)
        draw.rectangle([0, 0, layout.width, _BAR_H], fill=_BAR)
        draw.text((_PAD, (_BAR_H - 16) // 2), title.upper(), fill=_MUTED, font=_font(11, bold=True))
        if profile.get("name"):
            name = profile["name"][:24]
            x = layout.width - _PAD - int(draw.textlength(name, font=_font(11)))
            draw.text((x, (_BAR_H - 16) // 2), name, fill=_TEXT, font=_font(11))
            if profile.get("avatar") is not None:
                avatar = profile["avatar"].resize((_AVATAR, _AVATAR), Image.Resampling.LANCZOS)
                img.paste(avatar, (x - _AVATAR - 8, (_BAR_H - _AVATAR) // 2))
        return img

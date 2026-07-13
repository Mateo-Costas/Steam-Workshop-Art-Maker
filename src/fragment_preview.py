"""
fragment_preview.py - Fragment layout preview (PRO feature).

Shows exactly how a GIF/video gets CROPPED and split across Steam Workshop /
Artwork Showcase slots, on a fixed neutral background — no attempt to mimic
the real Steam profile page (its layout/fonts/spacing change over time and a
hand-drawn mockup would always drift from reality). This is honest about
what it shows: fragmentation only, not a profile simulation.

Optional "Perfil Personalizado" mode fetches your real Steam name + avatar
via the Steam Community XML API (no API key, no browser) and shows them in
a small label above the grid — profile must be public.

Preset keys match SteamProcessor.SHOWCASE_PRESETS exactly.
"""

import io
import logging
import os
import threading
import tkinter as tk
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont, ImageSequence, ImageTk

logger = logging.getLogger("WorkshopArtPRO.fragment_preview")

# ─── Fixed neutral palette (not trying to match live Steam UI) ────────────────
_C_BG     = (18,  24,  32)   # canvas background
_C_CARD   = (28,  38,  52)   # header bar fill
_C_SLOT   = (10,  16,  26)   # empty slot fill
_C_BORDER = (48,  64,  84)   # border lines
_C_ACCENT = (102, 192, 244)  # highlight
_C_TEXT   = (200, 212, 224)  # primary text
_C_MUTED  = (128, 143, 156)  # secondary text

# ─── Fixed layout constants ────────────────────────────────────────────────────
_PAD      = 18
_CW       = 700   # content width available for the slot grid
_BAR_H    = 40    # top bar: preset name + optional user label
_AV_SIZE  = 24    # small avatar shown in the top bar (personal mode only)

# ─── Preset catalogue — keys mirror SteamProcessor.SHOWCASE_PRESETS ──────────
_PRESETS: Dict[str, dict] = {
    # ── 1-slot ────────────────────────────────────────────────────────────────
    "featured_630": {
        "label": "Featured Artwork · 630×430 (1 slot grande)",
        "header": "FEATURED ARTWORK SHOWCASE",
        "layout": "single", "slots": 1, "tw": 630, "th": 430,
    },
    "artwork_single_630": {
        "label": "Artwork Showcase · 630×354 (1 slot, 16:9)",
        "header": "ARTWORK SHOWCASE",
        "layout": "single", "slots": 1, "tw": 630, "th": 354,
    },
    "screenshot_638": {
        "label": "Screenshot Showcase · 638×354 (1 slot)",
        "header": "SCREENSHOT SHOWCASE",
        "layout": "single", "slots": 1, "tw": 638, "th": 354,
    },
    # ── 2-slot ────────────────────────────────────────────────────────────────
    "artwork_2part": {
        "label": "Artwork · Main 506 + Side 100 (2 partes)",
        "header": "ARTWORK SHOWCASE",
        "layout": "main_side", "slots": 2, "mw": 506, "sw": 100, "th": 300,
    },
    # ── 4-slot horizontal ─────────────────────────────────────────────────────
    "artwork_4grid": {
        "label": "Artwork · 4 partes (4×245×245 cuadrado)",
        "header": "ARTWORK SHOWCASE",
        "layout": "hstrip", "slots": 4, "tw": 245, "th": 245,
    },
    "screenshot_4grid": {
        "label": "Screenshot · 4 partes (4×638×354)",
        "header": "SCREENSHOT SHOWCASE",
        "layout": "hstrip", "slots": 4, "tw": 638, "th": 354,
    },
    # ── 5-slot workshop ───────────────────────────────────────────────────────
    "workshop_5slot_150": {
        "label": "Workshop Showcase · 5×150×150",
        "header": "WORKSHOP SHOWCASE",
        "layout": "hstrip", "slots": 5, "tw": 150, "th": 150,
    },
    "workshop_5slot_119": {
        "label": "Workshop Showcase · 5×119×119 (tamaño nativo)",
        "header": "WORKSHOP SHOWCASE",
        "layout": "hstrip", "slots": 5, "tw": 119, "th": 119,
    },
    # ── panorama ──────────────────────────────────────────────────────────────
    "panorama_5_630": {
        "label": "Panorama · 5×630×360 (banner horizontal)",
        "header": "PANORAMA SHOWCASE",
        "layout": "hstrip", "slots": 5, "tw": 630, "th": 360,
    },
}

_DEFAULT_PRESET = "artwork_single_630"


# =============================================================================
# Fragment grid renderer
# =============================================================================

class _GridRenderer:
    """Renders a PIL Image: fixed background + the showcase slot grid only."""

    def canvas_size(self, preset_key: str) -> Tuple[int, int]:
        slots = self._slot_rects(preset_key)
        h = (max((y1 for (_, _, _, y1) in slots), default=0) + _PAD) if slots else _BAR_H + _PAD
        return _CW + 2 * _PAD, h

    def render(self, preset_key: str, *,
               name: Optional[str] = None,
               avatar_img: Optional[Image.Image] = None) -> Image.Image:
        w, h = self.canvas_size(preset_key)
        img = Image.new("RGB", (w, h), _C_BG)
        d = ImageDraw.Draw(img)
        self._draw_bar(img, d, preset_key, name, avatar_img)
        self._draw_slots(d, preset_key)
        return img

    def composite(self, template: Image.Image, frame: Image.Image,
                  preset_key: str) -> Image.Image:
        """
        Paste a correctly CROPPED portion of frame into each showcase slot.

          hstrip    → N equal horizontal slices (i-th vertical band)
          main_side → left band (main) / right band (side) by mw:sw ratio
          single    → full frame scaled to the single slot
        """
        result = template.copy()
        slots  = self._slot_rects(preset_key)
        if not slots:
            return result

        frame_rgb = frame.convert("RGB")
        fw, fh    = frame_rgb.size
        preset    = _PRESETS.get(preset_key, _PRESETS[_DEFAULT_PRESET])
        layout    = preset["layout"]

        if layout == "single":
            x0, y0, x1, y1 = slots[0]
            result.paste(frame_rgb.resize((x1 - x0, y1 - y0), Image.LANCZOS), (x0, y0))

        elif layout == "hstrip":
            n = len(slots)
            for i, (x0, y0, x1, y1) in enumerate(slots):
                crop = frame_rgb.crop((fw * i // n, 0, fw * (i + 1) // n, fh))
                result.paste(crop.resize((x1 - x0, y1 - y0), Image.LANCZOS), (x0, y0))

        elif layout == "main_side":
            ratio   = preset["mw"] / (preset["mw"] + preset["sw"])
            split_x = int(fw * ratio)
            x0, y0, x1, y1 = slots[0]
            result.paste(
                frame_rgb.crop((0, 0, split_x, fh)).resize((x1 - x0, y1 - y0), Image.LANCZOS),
                (x0, y0),
            )
            if len(slots) > 1:
                x0, y0, x1, y1 = slots[1]
                result.paste(
                    frame_rgb.crop((split_x, 0, fw, fh)).resize(
                        (x1 - x0, y1 - y0), Image.LANCZOS),
                    (x0, y0),
                )

        return result

    # ── drawing helpers ───────────────────────────────────────────────────────

    def _draw_bar(self, img: Image.Image, d: ImageDraw.ImageDraw, preset_key: str,
                  name: Optional[str], avatar_img: Optional[Image.Image]):
        preset = _PRESETS.get(preset_key, _PRESETS[_DEFAULT_PRESET])
        w = img.size[0]
        d.rectangle([0, 0, w, _BAR_H], fill=_C_CARD)
        d.text((_PAD, (_BAR_H - 14) // 2), preset["header"], fill=_C_MUTED,
               font=self._f(10, bold=True))

        if name:
            label = name if len(name) <= 22 else name[:21] + "…"
            tw = len(label) * 6 + 8
            tx = w - _PAD - tw
            if avatar_img is not None:
                av = avatar_img.resize((_AV_SIZE, _AV_SIZE), Image.LANCZOS).convert("RGB")
                tx -= _AV_SIZE + 8
                img.paste(av, (tx, (_BAR_H - _AV_SIZE) // 2))
                tx += _AV_SIZE + 8
            d.text((tx, (_BAR_H - 12) // 2), label, fill=_C_TEXT, font=self._f(9))

    def _draw_slots(self, d: ImageDraw.ImageDraw, preset_key: str):
        for (x0, y0, x1, y1) in self._slot_rects(preset_key):
            d.rectangle([x0, y0, x1, y1], fill=_C_SLOT, outline=_C_BORDER, width=1)
            cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
            sw = max(12, (x1 - x0) // 5)
            d.line([cx - sw, cy, cx + sw, cy], fill=_C_BORDER, width=1)
            d.line([cx, cy - sw, cx, cy + sw], fill=_C_BORDER, width=1)

    # ── slot geometry ─────────────────────────────────────────────────────────

    def _slot_rects(self, preset_key: str) -> List[Tuple[int, int, int, int]]:
        """Absolute (x0, y0, x1, y1) for every slot — scaled to fit within _CW."""
        preset = _PRESETS.get(preset_key, _PRESETS[_DEFAULT_PRESET])
        layout = preset["layout"]
        cx     = _PAD
        cy     = _BAR_H + _PAD
        cw     = _CW

        if layout == "single":
            sh = int(cw * preset["th"] / preset["tw"])
            return [(cx, cy, cx + cw, cy + sh)]

        elif layout == "hstrip":
            n  = preset["slots"]
            sw = cw // n
            sh = int(sw * preset["th"] / preset["tw"])
            gap = 2
            return [
                (cx + i * (sw + gap), cy, cx + i * (sw + gap) + sw, cy + sh)
                for i in range(n)
            ]

        elif layout == "main_side":
            total  = preset["mw"] + preset["sw"]
            mw_px  = int(cw * preset["mw"] / total) - 2
            sw_px  = cw - mw_px - 4
            sh_m   = int(mw_px * preset["th"] / preset["mw"])
            sh_s   = int(sw_px * preset["th"] / preset["sw"])
            return [
                (cx,             cy, cx + mw_px,             cy + sh_m),
                (cx + mw_px + 4, cy, cx + mw_px + 4 + sw_px, cy + sh_s),
            ]

        return []

    @staticmethod
    def _f(size: int, bold: bool = False) -> ImageFont.ImageFont:
        sysroot = os.environ.get("SystemRoot", "C:\\Windows")
        for name in (("segoeuib.ttf" if bold else "segoeui.ttf"), "arial.ttf"):
            try:
                return ImageFont.truetype(os.path.join(sysroot, "Fonts", name), size)
            except Exception:
                continue
        return ImageFont.load_default()


# =============================================================================
# Steam XML profile fetcher
# =============================================================================

class _ProfileFetcher:
    """
    Fetches public Steam profile data via the Community XML endpoint.
    No API key, no browser. Works for public profiles only.
    """

    _HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    }

    def fetch(self, profile_url: str, status_cb: Callable[[str], None]) -> dict:
        """Return {'name': str, 'avatar': PIL Image|None, 'online': bool}."""
        base = profile_url.rstrip("/")
        if "?xml=1" not in base:
            xml_url = base + "/?xml=1"
        else:
            xml_url = base

        status_cb("Conectando con Steam…")
        req = urllib.request.Request(xml_url, headers=self._HEADERS)
        try:
            with urllib.request.urlopen(req, timeout=12) as r:
                raw = r.read()
        except Exception as exc:
            raise RuntimeError(f"No se pudo conectar con Steam: {exc}") from exc

        try:
            root = ET.fromstring(raw)
        except ET.ParseError as exc:
            raise RuntimeError("Respuesta inesperada de Steam (¿perfil privado?)") from exc

        error = root.findtext("error")
        if error:
            raise RuntimeError(f"Perfil no disponible: {error}")

        name   = root.findtext("steamID") or "SteamUser"
        av_url = root.findtext("avatarFull") or root.findtext("avatarMedium") or ""
        state  = (root.findtext("onlineState") or "").lower()
        online = state in ("online", "in-game")

        av_img = None
        if av_url:
            status_cb("Descargando avatar…")
            try:
                req2 = urllib.request.Request(av_url, headers=self._HEADERS)
                with urllib.request.urlopen(req2, timeout=10) as r2:
                    av_img = Image.open(io.BytesIO(r2.read())).convert("RGB")
            except Exception:
                pass  # avatar is optional — render without it

        status_cb(f"Perfil cargado: {name}")
        return {"name": name, "avatar": av_img, "online": online}


# =============================================================================
# Public entry point
# =============================================================================

class FragmentPreviewSystem:
    """Opens the fragment layout preview dialog."""

    def __init__(self, theme_colors: dict):
        self.theme     = theme_colors
        self._renderer = _GridRenderer()
        self._photos: List[ImageTk.PhotoImage] = []

    # ── public ────────────────────────────────────────────────────────────────

    def create_fragment_preview(self, gif_path: Path, parent_window,
                                preset: str = _DEFAULT_PRESET):
        self._photos.clear()

        win = tk.Toplevel(parent_window)
        win.title("Fragment Preview — WorkshopArt")
        win.resizable(False, False)
        win.configure(bg="#0e1921")
        win.transient(parent_window)
        win.grab_set()

        frames, durations = self._load_gif(gif_path)
        if not frames:
            win.geometry("500x120")
            tk.Label(win, text="No se pudieron cargar los frames del GIF.",
                     bg="#0e1921", fg="#c6d4df", font=("Segoe UI", 11)).pack(pady=40)
            return

        # ── tab / control bar ─────────────────────────────────────────────────
        tabbar = tk.Frame(win, bg="#0e1921")
        tabbar.pack(fill="x", side="top")

        active_tab = tk.StringVar(value="grid")
        personal_data = {"name": None, "avatar": None}

        def _switch(mode: str):
            active_tab.set(mode)
            _render_active()

        tk.Button(tabbar, text="Grid de fragmentos",
                  command=lambda: _switch("grid"),
                  bg="#2a475e", fg="#c6d4df", relief="flat",
                  font=("Segoe UI", 10), padx=14, pady=6).pack(side="left")

        beta_row = tk.Frame(tabbar, bg="#0e1921")
        beta_row.pack(side="left")
        tk.Button(beta_row, text="Perfil Personalizado",
                  command=lambda: _switch("personal"),
                  bg="#1b2838", fg="#c6d4df", relief="flat",
                  font=("Segoe UI", 10), padx=14, pady=6).pack(side="left")
        tk.Label(beta_row, text="BETA", bg="#d29922", fg="#000",
                 font=("Segoe UI", 7, "bold"), padx=4, pady=1).pack(side="left", padx=(0, 8))

        # Preset selector
        sel = tk.Frame(tabbar, bg="#0e1921")
        sel.pack(side="left", padx=(16, 0))
        tk.Label(sel, text="Preset:", bg="#0e1921", fg="#7b8a97",
                 font=("Segoe UI", 9)).pack(side="left", padx=(0, 4))
        labels     = [v["label"] for v in _PRESETS.values()]
        key_by_lbl = {v["label"]: k for k, v in _PRESETS.items()}
        init_preset = preset if preset in _PRESETS else _DEFAULT_PRESET
        preset_var  = tk.StringVar(value=_PRESETS[init_preset]["label"])
        opt = tk.OptionMenu(sel, preset_var, *labels, command=lambda _: _render_active())
        opt.configure(bg="#2a475e", fg="#c6d4df", activebackground="#1b2838",
                      highlightthickness=0, relief="flat", font=("Segoe UI", 9))
        opt["menu"].configure(bg="#2a475e", fg="#c6d4df", font=("Segoe UI", 9))
        opt.pack(side="left")

        def _preset_key() -> str:
            return key_by_lbl.get(preset_var.get(), init_preset)

        # ── canvas (resized per preset) ───────────────────────────────────────
        canvas = tk.Canvas(win, bg="#1b2838", highlightthickness=0)
        canvas.pack(side="top")

        # ── personal profile panel ────────────────────────────────────────────
        personal_overlay = tk.Frame(win, bg="#1b2838")
        url_var    = tk.StringVar(value="https://steamcommunity.com/id/TU_PERFIL")
        status_var = tk.StringVar(value="")

        tk.Label(personal_overlay, text="URL de tu perfil Steam:",
                 bg="#1b2838", fg="#c6d4df", font=("Segoe UI", 11)).pack(pady=(48, 6))
        tk.Entry(personal_overlay, textvariable=url_var, width=58,
                 bg="#2a475e", fg="#c6d4df", insertbackground="#c6d4df",
                 relief="flat", font=("Segoe UI", 10)).pack(ipady=5)
        tk.Label(personal_overlay,
                 text=("Obtiene tu nombre y avatar reales desde Steam Community\n"
                       "y los muestra en la barra sobre el grid de fragmentos.\n"
                       "Tu perfil debe estar configurado como PÚBLICO."),
                 bg="#1b2838", fg="#7b8a97", font=("Segoe UI", 9),
                 justify="center").pack(pady=10)
        tk.Button(personal_overlay, text="  Cargar perfil y previsualizar  ",
                  bg="#66c0f4", fg="#000", font=("Segoe UI", 10, "bold"),
                  relief="flat", padx=12, pady=6,
                  command=lambda: self._run_personal(
                      url_var.get(), personal_data, _preset_key(),
                      status_var, win,
                      on_success=_animate,
                      on_error=lambda msg: status_var.set(msg),
                  )).pack()
        tk.Label(personal_overlay, textvariable=status_var,
                 bg="#1b2838", fg="#66c0f4", font=("Segoe UI", 9)).pack(pady=8)

        # ── animation state ───────────────────────────────────────────────────
        _anim = {"run": False, "idx": 0, "after_id": None}

        def _stop():
            _anim["run"] = False
            if _anim["after_id"]:
                try:
                    win.after_cancel(_anim["after_id"])
                except Exception:
                    pass
                _anim["after_id"] = None

        def _resize_canvas(key: str):
            w, h = self._renderer.canvas_size(key)
            canvas.configure(width=w, height=h)
            win.update_idletasks()
            bar_h = tabbar.winfo_reqheight()
            win.geometry(f"{w}x{h + bar_h}")
            self._center(win, w, h + bar_h)
            personal_overlay.place(x=0, y=0, width=w, height=h)

        def _animate(key: str):
            """Start looping animation over the resized grid template."""
            _stop()
            personal_overlay.place_forget()
            template = self._renderer.render(
                key, name=personal_data["name"], avatar_img=personal_data["avatar"])
            _anim["run"] = True
            _anim["idx"] = 0

            def _tick():
                if not _anim["run"]:
                    return
                i   = _anim["idx"] % len(frames)
                img = self._renderer.composite(template, frames[i], key)
                ph  = ImageTk.PhotoImage(img)
                self._photos = [ph]            # keep reference alive
                canvas.delete("all")
                canvas.create_image(0, 0, image=ph, anchor="nw")
                _anim["idx"] += 1
                delay = max(50, durations[i] if durations else 80)
                _anim["after_id"] = win.after(delay, _tick)

            _tick()

        def _show_grid():
            key = _preset_key()
            _resize_canvas(key)
            personal_overlay.place_forget()
            _animate(key)

        def _show_personal():
            _stop()
            key = _preset_key()
            _resize_canvas(key)

        def _render_active():
            if active_tab.get() == "grid":
                _show_grid()
            else:
                _show_personal()

        win.protocol("WM_DELETE_WINDOW", lambda: (_stop(), win.destroy()))
        win.after(80, _render_active)

    # ── private helpers ───────────────────────────────────────────────────────

    def _run_personal(self, url: str, personal_data: dict, preset_key: str,
                      status_var: tk.StringVar, win: tk.Toplevel,
                      on_success: Callable, on_error: Callable[[str], None]):
        """
        Fetch profile data in a background thread, then call on_success(key)
        on the main thread. on_success IS _animate — it re-renders with the
        fetched name/avatar and hides the overlay automatically.
        """
        status_var.set("Conectando con Steam…")

        def _task():
            try:
                data = _ProfileFetcher().fetch(url, lambda m: win.after(0, lambda: status_var.set(m)))
                win.after(0, lambda: status_var.set("Renderizando preview…"))

                personal_data["name"]   = data["name"]
                personal_data["avatar"] = data["avatar"]

                win.after(0, lambda k=preset_key: on_success(k))
                win.after(200, lambda: status_var.set(f"Mostrando como: {data['name']}"))

            except Exception as exc:
                logger.error("Personal preview error: %s", exc)
                win.after(0, lambda m=str(exc): on_error(f"Error: {m}"))

        threading.Thread(target=_task, daemon=True).start()

    @staticmethod
    def _load_gif(path: Path) -> Tuple[List[Image.Image], List[int]]:
        frames, durations = [], []
        try:
            with Image.open(path) as img:
                for f in ImageSequence.Iterator(img):
                    frames.append(f.convert("RGBA").convert("RGB"))
                    durations.append(f.info.get("duration", 80))
        except Exception as exc:
            logger.error("Could not load GIF: %s", exc)
        return frames, durations

    @staticmethod
    def _center(win: tk.Toplevel, w: int, h: int):
        win.update_idletasks()
        x = (win.winfo_screenwidth()  - w) // 2
        y = (win.winfo_screenheight() - h) // 2
        win.geometry(f"{w}x{h}+{x}+{y}")

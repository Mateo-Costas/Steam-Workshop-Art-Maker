"""
upload_tool.py - Mini app independiente para auto-subir GIFs a Steam Workshop.

Privado, gitignoreado. Reusa src/steam_uploader.py.

Uso:
    python upload_tool.py

Requisitos:
    - requests (ya en requirements.txt)
    - browser_cookie3 (opcional pero recomendado: pip install browser_cookie3)
    - Firefox logueado en steamcommunity.com (cierra Firefox antes de subir)
      O un fichero steam_cookies.json en la raíz con sessionid+steamLoginSecure.
"""
from __future__ import annotations
import sys
import threading
from pathlib import Path
from tkinter import filedialog, messagebox
from queue import Queue, Empty

import customtkinter as ctk

# Importar el uploader desde src/
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "src"))
try:
    import steam_uploader
except ImportError as e:
    messagebox.showerror(
        "Error",
        "No se encontró src/steam_uploader.py.\n\n"
        "Este módulo es privado y debe existir en la carpeta src/.\n\n"
        f"Detalle: {e}"
    )
    sys.exit(1)


ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# Preset → (upload_mode, auto_spoof, label)
UPLOAD_PRESETS: dict[str, tuple[str, bool, str]] = {
    "featured_630":     ("artwork",    False, "Featured Artwork 630×H (1 slot)"),
    "artwork_single_630": ("artwork",  False, "Artwork single 630×354 (sin side image, 16:9)"),
    "artwork_2part":    ("artwork",    False, "Artwork 506+100 (main+side, alto libre)"),
    "artwork_4grid":    ("artwork",    False, "Artwork 4-grid 4×245"),
    "panorama_5_630":   ("artwork",    False, "Panorama artwork 5×630×360"),
    "screenshot_638":   ("screenshot", False, "Screenshot Showcase 638×354 (1 slot)"),
    "screenshot_4grid": ("screenshot", False, "Screenshot 4-grid 4×638×354"),
    "workshop_5slot_150": ("workshop", False, "Workshop 5×150×150"),
    "workshop_5slot_119": ("workshop", False, "Workshop 5×119×119 (nativo)"),
    "manual_artwork":   ("artwork",    False, "— Manual: Artwork (file_type=3)"),
    "manual_screenshot":("screenshot", True,  "— Manual: Screenshot (file_type=5)"),
    "manual_workshop":  ("workshop",   False, "— Manual: Workshop (file_type=0)"),
}
_PRESET_LABELS = [v[2] for v in UPLOAD_PRESETS.values()]
_PRESET_KEYS   = list(UPLOAD_PRESETS.keys())


class UploadApp(ctk.CTk):
    def __init__(self, preloaded_files: list = None, preset_key: str = None):
        super().__init__()
        self.title("Steam Workshop Auto-Uploader")
        self.geometry("760x760")

        self._queue: Queue = Queue()
        self._files: list[Path] = []
        self._rows: dict[Path, dict] = {}   # path -> {"var": BooleanVar, "row": frame}
        self._uploading = False

        self._build_ui()
        self._poll_queue()
        self._update_cookie_banner()

        if preset_key and preset_key in UPLOAD_PRESETS:
            label = UPLOAD_PRESETS[preset_key][2]
            self.preset_var.set(label)
            self._on_preset_change(label)

        for p in (preloaded_files or []):
            self._add_one(Path(p))

    # ---------------- UI ----------------

    def _build_ui(self):
        # Banner cookies
        self.banner = ctk.CTkLabel(self, text="", height=32, anchor="w",
                                   font=("Segoe UI", 11))
        self.banner.pack(fill="x", padx=12, pady=(10, 2))

        # Título prefix
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=12, pady=6)
        ctk.CTkLabel(top, text="Prefijo del título:").pack(side="left")
        self.title_var = ctk.StringVar(value="WorkshopArt")
        ctk.CTkEntry(top, textvariable=self.title_var, width=240).pack(side="left", padx=8)
        ctk.CTkLabel(top, text="(se añade ' - Parte i/N')",
                     text_color="#888").pack(side="left")

        # Preset / modo upload
        preset_row = ctk.CTkFrame(self, fg_color="transparent")
        preset_row.pack(fill="x", padx=12, pady=(4, 0))
        ctk.CTkLabel(preset_row, text="Preset:").pack(side="left")
        self.preset_var = ctk.StringVar(value=_PRESET_LABELS[0])
        self.preset_combo = ctk.CTkComboBox(
            preset_row, values=_PRESET_LABELS, variable=self.preset_var,
            width=340, command=self._on_preset_change)
        self.preset_combo.pack(side="left", padx=8)

        self.mode_label = ctk.CTkLabel(preset_row, text="", width=200,
                                       font=("Segoe UI", 11), text_color="#888")
        self.mode_label.pack(side="left", padx=6)

        # fila extra: workshop appid + spoof override
        extra_row = ctk.CTkFrame(self, fg_color="transparent")
        extra_row.pack(fill="x", padx=12, pady=(2, 0))
        self.appid_label = ctk.CTkLabel(extra_row, text="appid Workshop:")
        self.appid_label.pack(side="left")
        self.workshop_appid_var = ctk.StringVar(value="480")
        self.workshop_appid_entry = ctk.CTkEntry(extra_row,
                                                  textvariable=self.workshop_appid_var, width=80)
        self.workshop_appid_entry.pack(side="left", padx=(4, 16))
        self.spoof_var = ctk.BooleanVar(value=False)
        self.spoof_check = ctk.CTkCheckBox(extra_row, text="Spoof dims 1000×1 (solo panorama)",
                                            variable=self.spoof_var)
        self.spoof_check.pack(side="left")

        # fila pubids: actualizar items existentes en vez de crear nuevos
        pubids_row = ctk.CTkFrame(self, fg_color="transparent")
        pubids_row.pack(fill="x", padx=12, pady=(2, 0))
        ctk.CTkLabel(pubids_row, text="IDs existentes:").pack(side="left")
        self.pubids_var = ctk.StringVar(value="")
        ctk.CTkEntry(pubids_row, textvariable=self.pubids_var, width=340,
                     placeholder_text="Dejar vacío = crear nuevo. Ej: 123456,789012").pack(
                         side="left", padx=(4, 8))
        ctk.CTkLabel(pubids_row, text="(uno por archivo en orden)",
                     text_color="#888", font=("Segoe UI", 10)).pack(side="left")

        # hidden vars derivados del preset
        self.mode_var = ctk.StringVar(value="artwork")
        self._on_preset_change(_PRESET_LABELS[0])

        # Botones superiores
        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.pack(fill="x", padx=12, pady=(0, 6))
        ctk.CTkButton(btns, text="➕ Añadir archivos…",
                      command=self._add_files).pack(side="left", padx=4)
        ctk.CTkButton(btns, text="📁 Añadir carpeta",
                      command=self._add_folder).pack(side="left", padx=4)
        ctk.CTkButton(btns, text="❌ Quitar marcados",
                      command=self._remove_checked,
                      fg_color="#7f1d1d", hover_color="#991b1b").pack(side="left", padx=4)
        ctk.CTkButton(btns, text="Limpiar lista",
                      command=self._clear_all).pack(side="left", padx=4)

        # Lista scrollable
        self.list_frame = ctk.CTkScrollableFrame(self, height=260, label_text="Archivos a subir")
        self.list_frame.pack(fill="both", expand=True, padx=12, pady=6)

        # Upload
        up = ctk.CTkFrame(self, fg_color="transparent")
        up.pack(fill="x", padx=12, pady=4)
        self.upload_btn = ctk.CTkButton(up, text="🚀 Subir seleccionados a Steam",
                                        command=self._on_upload,
                                        fg_color="#16a34a", hover_color="#15803d",
                                        height=40, font=("Segoe UI", 13, "bold"))
        self.upload_btn.pack(side="left", padx=4)
        self.progress = ctk.CTkProgressBar(up)
        self.progress.set(0)
        self.progress.pack(side="left", padx=10, fill="x", expand=True)

        # Log
        self.log = ctk.CTkTextbox(self, height=140, font=("Consolas", 10))
        self.log.pack(fill="both", expand=False, padx=12, pady=(4, 10))
        self.log.configure(state="disabled")

    def _on_preset_change(self, label: str):
        try:
            idx = _PRESET_LABELS.index(label)
        except ValueError:
            idx = 0
        key = _PRESET_KEYS[idx]
        mode, auto_spoof, _ = UPLOAD_PRESETS[key]
        self.mode_var.set(mode)

        mode_txt = {"artwork": "Artwork  /767/3/", "screenshot": "Screenshot  /767/5/",
                    "workshop": "Workshop  file_type=0"}.get(mode, mode)
        spoof_note = "  +spoof dims" if auto_spoof else ""
        self.mode_label.configure(text=f"→ {mode_txt}{spoof_note}")

        ws_state = "normal" if mode == "workshop" else "disabled"
        self.workshop_appid_entry.configure(state=ws_state)
        self.appid_label.configure(text_color="#ccc" if mode == "workshop" else "#555")

        # auto-spoof visible/hidden based on mode (screenshot already spoofs internally)
        if mode == "screenshot":
            self.spoof_check.configure(state="disabled",
                                        text="Spoof dims (auto en screenshot)")
            self.spoof_var.set(False)
        else:
            self.spoof_check.configure(state="normal",
                                        text="Spoof dims (1000×1) override")

        self._auto_spoof = auto_spoof

    def _effective_spoof(self) -> bool:
        return self._auto_spoof or bool(self.spoof_var.get())

    def _update_cookie_banner(self):
        src = steam_uploader.cookies_source()
        if src == "firefox":
            self.banner.configure(text="✅ Cookies: Firefox (automático)",
                                  text_color="#22c55e")
        elif src == "file":
            self.banner.configure(text="✅ Cookies: steam_cookies.json",
                                  text_color="#22c55e")
        else:
            self.banner.configure(
                text="⚠️ Sin cookies. Instala browser_cookie3 y loguéate en Firefox, "
                     "o crea steam_cookies.json en la raíz.",
                text_color="#f59e0b")

    # ---------------- File list ----------------

    def _add_files(self):
        paths = filedialog.askopenfilenames(
            title="Seleccionar imágenes a subir",
            filetypes=[
                ("Imágenes", "*.gif *.jpg *.jpeg *.png *.bmp *.webp"),
                ("GIF", "*.gif"), ("JPEG", "*.jpg *.jpeg"),
                ("PNG", "*.png"), ("Todos", "*.*"),
            ],
        )
        for p in paths:
            self._add_one(Path(p))

    def _add_folder(self):
        folder = filedialog.askdirectory(title="Carpeta con imágenes")
        if not folder:
            return
        _img_exts = {'.gif', '.jpg', '.jpeg', '.png', '.bmp', '.webp'}
        all_imgs = [p for p in Path(folder).iterdir()
                    if p.is_file() and p.suffix.lower() in _img_exts]
        for p in steam_uploader._sort_by_part(all_imgs):
            self._add_one(p)

    def _add_one(self, path: Path):
        path = path.resolve()
        if path in self._rows:
            return
        if not path.exists():
            return
        var = ctk.BooleanVar(value=True)
        row = ctk.CTkFrame(self.list_frame, fg_color="transparent")
        row.pack(fill="x", pady=2)
        ctk.CTkCheckBox(row, text="", variable=var, width=24).pack(side="left", padx=(0, 6))
        size_mb = path.stat().st_size / (1024 * 1024)
        ctk.CTkLabel(row, text=f"{path.name}  —  {size_mb:.2f} MB",
                     anchor="w").pack(side="left", fill="x", expand=True)
        self._rows[path] = {"var": var, "row": row}
        self._files.append(path)

    def _remove_checked(self):
        to_remove = [p for p, d in self._rows.items() if d["var"].get()]
        for p in to_remove:
            self._rows[p]["row"].destroy()
            del self._rows[p]
            self._files.remove(p)

    def _clear_all(self):
        for d in self._rows.values():
            d["row"].destroy()
        self._rows.clear()
        self._files.clear()

    # ---------------- Upload ----------------

    def _on_upload(self):
        if self._uploading:
            return
        selected = [p for p, d in self._rows.items() if d["var"].get()]
        if not selected:
            messagebox.showwarning("Nada marcado", "Marca al menos un archivo.")
            return
        if not steam_uploader.cookies_configured():
            messagebox.showerror(
                "Sin cookies",
                "No se encontraron cookies de Steam.\n\n"
                "Opciones:\n"
                "1) pip install browser_cookie3 + loguéate en Firefox + cierra Firefox.\n"
                "2) Crea steam_cookies.json en la raíz con sessionid y steamLoginSecure."
            )
            return
        if not messagebox.askyesno("Confirmar",
                                   f"Subir {len(selected)} archivos a Steam Workshop.\n\n"
                                   "Asegúrate de que Firefox esté CERRADO si usas sus cookies.\n\n"
                                   "¿Continuar?"):
            return

        self._uploading = True
        self.upload_btn.configure(state="disabled", text="Subiendo…")
        self.progress.set(0)
        self._logln(f"=== Subiendo {len(selected)} archivos ===")

        title_prefix = (self.title_var.get() or "WorkshopArt").strip()
        mode = self.mode_var.get()
        workshop_appid = (self.workshop_appid_var.get() or "480").strip()
        spoof = self._effective_spoof()
        pubids_raw = self.pubids_var.get().strip()
        pubids = ([s.strip() for s in pubids_raw.replace(";", ",").split(",")
                   if s.strip().isdigit()]
                  if pubids_raw else [])
        thread = threading.Thread(target=self._upload_worker,
                                  args=(selected, title_prefix, mode, workshop_appid, spoof, pubids),
                                  daemon=True)
        thread.start()

    def _upload_worker(self, files: list[Path], title_prefix: str,
                       mode: str = "artwork", workshop_appid: str = "480",
                       spoof_dimensions: bool = False, pubids: list = None):
        total = len(files)

        def progress_cb(i, total_, msg):
            self._queue.put(("log", msg))
            self._queue.put(("progress", i / total_))

        try:
            results = steam_uploader.upload_fragments_playwright(
                files, title_prefix=title_prefix, mode=mode,
                workshop_appid=workshop_appid,
                spoof_dimensions=spoof_dimensions,
                pubids=pubids or [],
                progress_cb=progress_cb)
            ok = sum(1 for _, good, _ in results if good)
            summary = f"Subidos: {ok}/{total}"
            self._queue.put(("log", ""))
            self._queue.put(("log", f"=== {summary} ==="))
            for path, good, msg in results:
                tag = "OK " if good else "ERR"
                self._queue.put(("log", f"[{tag}] {path.name}: {msg}"))
            self._queue.put(("done", summary))
        except Exception as e:
            self._queue.put(("log", f"ERROR crítico: {e}"))
            self._queue.put(("done", f"Error: {e}"))

    # ---------------- Queue poll ----------------

    def _poll_queue(self):
        try:
            while True:
                kind, payload = self._queue.get_nowait()
                if kind == "log":
                    self._logln(payload)
                elif kind == "progress":
                    self.progress.set(payload)
                elif kind == "done":
                    self._uploading = False
                    self.upload_btn.configure(state="normal",
                                              text="🚀 Subir seleccionados a Steam")
                    self.progress.set(1.0)
                    messagebox.showinfo("Terminado", payload)
        except Empty:
            pass
        self.after(120, self._poll_queue)

    def _logln(self, text: str):
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")


if __name__ == "__main__":
    _preload = []
    _preset_key = None
    if '--fragments' in sys.argv:
        idx = sys.argv.index('--fragments')
        _preload = [Path(p) for p in sys.argv[idx + 1:] if not p.startswith('--')]
    if '--preset' in sys.argv:
        idx = sys.argv.index('--preset')
        if idx + 1 < len(sys.argv):
            _preset_key = sys.argv[idx + 1]
    app = UploadApp(preloaded_files=_preload, preset_key=_preset_key)
    app.mainloop()

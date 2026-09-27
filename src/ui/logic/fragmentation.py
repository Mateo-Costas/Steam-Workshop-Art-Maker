"""ui.logic.fragmentation - fragment with a preset, size optimiser and the 1-click pipeline."""
import os
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox
from tkinter.simpledialog import askfloat

import customtkinter as ctk

from i18n import t
from processing.common import STEAM_MAX_BYTES
from ui import theme
from ui.logic.common import STEAM_UPLOAD_URL, VIDEO_EXTS, steam_js_snippet
from ui.theme import Colors


class FragmentationMixin:
    """Showcase fragmentation, size optimisation and result dialogs."""

    def preset_title(self, preset: str) -> str:
        """Translated display name of a preset."""
        return t(f"preset_{preset}", fallback=self.processor.SHOWCASE_PRESETS[preset]["desc"])

    # ------------------------------------------------------------------
    # Fragment
    # ------------------------------------------------------------------
    def fragment_with_preset(self, preset: str) -> None:
        """Cut the current file into the parts of ``preset`` (background thread)."""
        if not self._require_file():
            return
        source = self.current_file

        def process():
            self.log_message(f"=== Fragmentar {source.name}: {preset} ===")
            self.update_status(t("status_fragmenting", fallback="Fragmentando..."), 10, "✂️")
            ok = self.processor.fragment_media(
                source, preset,
                progress_cb=lambda message: self.update_status(message, None, "✂️"),
                should_cancel=self._is_cancelled)
            if not ok:
                raise RuntimeError(self.processor._last_split_error
                                   or t("err_fragment", fallback="La fragmentación ha fallado"))
            fragments = self.processor.list_fragments(source)
            for path in fragments:
                self.log_message(f"Creado: {path.name} ({path.stat().st_size / 1048576:.2f} MB)",
                                 "SUCCESS")
            self.update_status(t("status_done", fallback="Completado"), 100, "✅")
            self.update_queue.put((self.show_fragment_result, (source, preset, fragments)))

        self._run_cancellable(process, t("fragment_now", fallback="Fragmentar"))

    def show_fragment_result(self, source: Path, preset: str, fragments: list) -> None:
        """Result dialog: fragments, the console snippet for this preset and upload actions."""
        cfg = self.processor.SHOWCASE_PRESETS[preset]
        js_code = steam_js_snippet(cfg["upload_hint"], cfg.get("spoof_dims", False))
        total_mb = sum(p.stat().st_size for p in fragments) / 1048576

        dlg = ctk.CTkToplevel(self.root)
        dlg.title(t("fragments_ready", fallback="Fragmentos generados"))
        dlg.geometry("660x560")
        dlg.transient(self.root)
        dlg.after(50, dlg.grab_set)

        ctk.CTkLabel(dlg, text=self.preset_title(preset), font=theme.font("HEADING")).pack(pady=(14, 2))
        ctk.CTkLabel(dlg, text=t("fragments_summary", fallback="{n} archivo(s) · {mb:.2f} MB en total",
                                 n=len(fragments), mb=total_mb),
                     font=theme.font("CAPTION"), text_color=Colors.TEXT_SECONDARY).pack()

        files = ctk.CTkScrollableFrame(dlg, height=130, fg_color=Colors.BG_SECONDARY)
        files.pack(fill="x", padx=14, pady=8)
        for path in fragments:
            size = path.stat().st_size
            mark = "✅" if size <= STEAM_MAX_BYTES else "❌"
            ctk.CTkLabel(files, text=f"{mark}  {path.name}  —  {size / 1048576:.2f} MB",
                         font=theme.font("MONO_SMALL"), anchor="w").pack(anchor="w", padx=6)

        ctk.CTkLabel(dlg, text=t("js_instructions", fallback="En la página de subida de Steam, abre la "
                                                             "consola (F12 → Console) y pega esto ANTES de guardar:"),
                     font=theme.font("SMALL"), wraplength=620, justify="left").pack(anchor="w", padx=14)
        js_box = ctk.CTkTextbox(dlg, height=100, font=theme.font("MONO_SMALL"))
        js_box.pack(fill="x", padx=14, pady=(4, 6))
        js_box.insert("end", js_code)
        js_box.configure(state="disabled")
        if preset == "artwork_2part":
            ctk.CTkLabel(dlg, text=t("artwork_2part_hint",
                                     fallback="Sube los dos archivos y en Editar perfil → Artwork "
                                              "Showcase asigna el principal y el lateral a su hueco."),
                         font=theme.font("CAPTION"), text_color=Colors.WARNING,
                         wraplength=620, justify="left").pack(anchor="w", padx=14)

        buttons = ctk.CTkFrame(dlg, fg_color="transparent")
        buttons.pack(fill="x", padx=14, pady=10)
        copy_btn = ctk.CTkButton(buttons, text=t("copy_js", fallback="Copiar JS"), width=110)

        def copy_js():
            dlg.clipboard_clear()
            dlg.clipboard_append(js_code)
            copy_btn.configure(text=t("copied", fallback="¡Copiado!"))
            dlg.after(2000, lambda: copy_btn.winfo_exists()
                      and copy_btn.configure(text=t("copy_js", fallback="Copiar JS")))

        copy_btn.configure(command=copy_js)
        copy_btn.pack(side="left", padx=4)
        folder = fragments[0].parent if fragments else self.processor.get_fragments_dir(source)
        ctk.CTkButton(buttons, text=t("open_fragments_folder", fallback="Abrir carpeta"), width=120,
                      command=lambda: os.startfile(folder)).pack(side="left", padx=4)
        ctk.CTkButton(buttons, text=t("open_workshop", fallback="Abrir Steam"), width=110,
                      command=lambda: webbrowser.open(STEAM_UPLOAD_URL)).pack(side="left", padx=4)
        ctk.CTkButton(buttons, text=t("upload_tool", fallback="Upload Tool"), width=120,
                      fg_color="#16a34a", hover_color="#15803d",
                      command=lambda: (dlg.destroy(), self._launch_upload_tool(fragments, preset))
                      ).pack(side="left", padx=4)
        ctk.CTkButton(buttons, text=t("close_btn", fallback="Cerrar"), width=80,
                      fg_color=Colors.BG_TERTIARY, command=dlg.destroy).pack(side="right", padx=4)

    # ------------------------------------------------------------------
    # Size optimiser
    # ------------------------------------------------------------------
    def optimize_to_steam_limit(self):
        """Pick GIFs and re-encode them under a size cap (5 MB by default).

        Several files are optimised together with one shared strategy so a
        set of fragments stays in sync.
        """
        initial = str(self.current_file.parent) if self.current_file else ""
        paths = filedialog.askopenfilenames(
            parent=self.root, initialdir=initial,
            title=t("pick_gifs_to_optimize", fallback="Selecciona los GIF a optimizar"),
            filetypes=[("GIF", "*.gif")])
        if not paths:
            return
        max_mb = askfloat(t("optimize_size", fallback="Optimizar ≤ 5 MB"),
                          t("ask_max_mb", fallback="Tamaño máximo por archivo (MB).\n"
                                                   "Steam rechaza más de 5 MB."),
                          initialvalue=5.0, minvalue=0.5, maxvalue=20.0, parent=self.root)
        if max_mb is None:
            return
        files = [Path(p) for p in paths]

        def process():
            self.update_status(t("status_optimizing", fallback="Optimizando..."), 10, "🎯")
            outputs = self.processor.shrink_batch_to_size_cap(
                files, max_mb=max_mb,
                progress_cb=lambda message: self.log_message(f"   {message}"),
                should_cancel=self._is_cancelled)
            lines = []
            for src, out in zip(files, outputs):
                if out is None:
                    lines.append(f"❌ {src.name}")
                else:
                    before, after = src.stat().st_size / 1048576, out.stat().st_size / 1048576
                    lines.append(f"✅ {src.name}: {before:.2f} → {after:.2f} MB")
            self.update_status(t("status_done", fallback="Completado"), 100, "✅")
            report = "\n".join(lines)
            if all(outputs):
                folder = next(o for o in outputs if o).parent
                self._ui_info(t("optimize_size", fallback="Optimizar ≤ 5 MB"),
                              report + "\n\n" + t("saved_in", fallback="Guardado en:\n{path}", path=folder))
            else:
                self._ui_warn(t("optimize_size", fallback="Optimizar ≤ 5 MB"),
                              report + "\n\n" + t("optimize_failed",
                                                  fallback="No se pudo bajar del límite: recorta la "
                                                           "duración del GIF."))

        self._run_cancellable(process, t("optimize_size", fallback="Optimizar ≤ 5 MB"))

    # ------------------------------------------------------------------
    # 1-click pipeline
    # ------------------------------------------------------------------
    def run_full_pipeline(self, preset: str = "workshop_5part"):
        """AI upscale (if models are installed) + color adjustments + fragmentation."""
        if not self._require_file():
            return
        model_id = self.selected_model_id()
        use_ai = bool(model_id)
        # Color adjustments work on GIFs and images: a video needs the AI step first.
        enhance = self.enhance_colors_var.get() and (
            use_ai or self.current_file.suffix.lower() not in VIDEO_EXTS)
        steps = []
        if use_ai:
            steps.append(t("pipeline_step_ai", fallback="Mejorar con IA ({model})", model=model_id))
        if enhance:
            steps.append(t("pipeline_step_colors", fallback="Aplicar los ajustes de color"))
        steps.append(t("pipeline_step_fragment", fallback="Fragmentar: {preset}",
                       preset=self.preset_title(preset)))
        if not messagebox.askyesno(
                t("pipeline_one_click", fallback="Pipeline 1-clic"),
                t("pipeline_confirm", fallback="Se ejecutará todo automáticamente:\n\n{steps}\n\n"
                                               "Puede tardar varios minutos. ¿Continuar?",
                  steps="\n".join(f"{i}. {s}" for i, s in enumerate(steps, 1))),
                parent=self.root):
            return
        source, use_gpu, adjust = self.current_file, self.gpu_var.get(), self._color_values()

        def process():
            work = source
            if use_ai:
                self.log_message(f"[Pipeline] IA con {model_id}")
                work = self._ai_upscale(work, model_id, use_gpu, progress_range=(5, 60))
            if enhance:
                self.update_status(t("status_colors", fallback="Mejorando colores..."), 65, "🎨")
                work = self.processor.enhance_colors(work, **adjust)
            self._raise_if_cancelled()
            self.update_status(t("status_fragmenting", fallback="Fragmentando..."), 70, "✂️")
            ok = self.processor.fragment_media(
                work, preset, progress_cb=lambda message: self.update_status(message, None, "✂️"),
                should_cancel=self._is_cancelled)
            if not ok:
                raise RuntimeError(self.processor._last_split_error
                                   or t("err_fragment", fallback="La fragmentación ha fallado"))
            self.current_file = work
            self.update_queue.put((self.show_file_info, ()))
            fragments = self.processor.list_fragments(work)
            self.update_status(t("status_done", fallback="Completado"), 100, "✅")
            self.log_message("[Pipeline] completado", "SUCCESS")
            self.update_queue.put((self.show_fragment_result, (work, preset, fragments)))

        self._run_cancellable(process, t("pipeline_one_click", fallback="Pipeline 1-clic"))

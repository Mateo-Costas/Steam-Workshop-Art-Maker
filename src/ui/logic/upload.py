"""ui.logic.upload - getting fragments onto Steam: snippets, Upload Tool, profile check, ZIP."""
import re
import subprocess
import sys
import threading
import urllib.request
import zipfile
from typing import Optional

import customtkinter as ctk

from app_paths import APP_DIR
from i18n import t
from processing.common import _NO_WINDOW_FLAGS
from ui import theme
from ui.logic.common import STEAM_UPLOAD_URL, steam_js_snippet
from ui.theme import Colors


class UploadMixin:
    """Upload helpers for step 4 and the fragment result dialog."""

    def current_fragments_preset(self) -> Optional[str]:
        """Preset used for the fragments of the current file (read from their manifest)."""
        if not self.current_file:
            return None
        manifest = self.processor.read_fragments_manifest(self.current_file)
        preset = (manifest.get("parametros") or {}).get("preset")
        if preset in self.processor.SHOWCASE_PRESETS:
            return preset
        # Manifests written by older versions only name the operation.
        legacy = {"fragmentar_steam": "workshop_5part",
                  "fragmentar_artwork_showcase": "artwork_2part",
                  "fragmentar_artwork_showcase_image": "artwork_2part"}
        operation = manifest.get("operacion", "")
        if operation in legacy:
            return legacy[operation]
        match = re.match(r"(?:fragmentar_)?showcase(?:_image)?_(.+)$", operation)
        return match.group(1) if match and match.group(1) in self.processor.SHOWCASE_PRESETS else None

    def steam_js_for_current(self) -> str:
        """Console snippet matching the current file's fragments (workshop if unknown)."""
        preset = self.current_fragments_preset()
        if not preset:
            return steam_js_snippet("workshop")
        cfg = self.processor.SHOWCASE_PRESETS[preset]
        return steam_js_snippet(cfg["upload_hint"], cfg.get("spoof_dims", False))

    def _copy_steam_js(self):
        """Copy the right console snippet for the current fragments to the clipboard."""
        self.root.clipboard_clear()
        self.root.clipboard_append(self.steam_js_for_current())
        self.update_status(t("js_copied", fallback="Snippet JS copiado: pégalo en la consola "
                                                   "del navegador (F12)"), None, "📋")

    def _launch_upload_tool(self, fragments=None, preset: Optional[str] = None):
        """Open the Upload Tool in its own process with the fragments preloaded."""
        if fragments is None and self.current_file:
            fragments = self.processor.list_fragments(self.current_file)
            preset = preset or self.current_fragments_preset()
        args = []
        if fragments:
            args += ["--fragments"] + [str(f) for f in fragments]
        if preset:
            args += ["--preset", preset]
        if getattr(sys, "frozen", False):
            cmd = [sys.executable, "--upload-tool"] + args
        else:
            cmd = [sys.executable, str(APP_DIR / "upload_tool.py")] + args
        try:
            subprocess.Popen(cmd, cwd=str(APP_DIR), **_NO_WINDOW_FLAGS)
        except OSError as e:
            self._ui_error(t("upload_tool", fallback="Upload Tool"), str(e))

    # ------------------------------------------------------------------
    # Steam profile check
    # ------------------------------------------------------------------
    def validate_steam_profile(self):
        """Check that a Steam profile is public and has level 10+ (needed for showcases)."""
        from fragment_preview import _ProfileFetcher

        dlg = ctk.CTkToplevel(self.root)
        dlg.title(t("validate_profile", fallback="Validar perfil"))
        dlg.geometry("460x280")
        dlg.transient(self.root)
        dlg.after(50, dlg.grab_set)
        ctk.CTkLabel(dlg, text=t("profile_prompt", fallback="Tu nombre personalizado o la URL de tu perfil:"),
                     font=theme.font("SMALL")).pack(pady=(18, 4))
        entry_var = ctk.StringVar(value=self.config.get("ui.steam_vanity", ""))
        ctk.CTkEntry(dlg, textvariable=entry_var, width=360).pack(pady=6)
        result_label = ctk.CTkLabel(dlg, text="", font=theme.font("SMALL"), justify="left",
                                    wraplength=410)
        result_label.pack(pady=6, padx=16)

        def show(text, color=Colors.TEXT_SECONDARY):
            self.update_queue.put((lambda: result_label.winfo_exists()
                                   and result_label.configure(text=text, text_color=color), ()))

        def validate():
            raw = entry_var.get().strip()
            if not raw:
                return
            self.config.set("ui.steam_vanity", raw)
            if raw.startswith("http"):
                url = raw
            elif raw.isdigit() and len(raw) == 17:
                url = f"https://steamcommunity.com/profiles/{raw}"
            else:
                url = f"https://steamcommunity.com/id/{raw}"

            def worker():
                try:
                    show(t("profile_checking", fallback="Consultando Steam..."))
                    data = _ProfileFetcher().fetch(url, lambda _m: None)
                    lines = [t("profile_found", fallback="✅ Perfil encontrado: {name}", name=data["name"])]
                    level = None
                    try:
                        request = urllib.request.Request(url, headers=_ProfileFetcher._HEADERS)
                        with urllib.request.urlopen(request, timeout=12) as response:
                            html = response.read().decode("utf-8", errors="replace")
                        match = re.search(r'friendPlayerLevelNum">\s*(\d+)', html)
                        level = int(match.group(1)) if match else None
                    except OSError:
                        pass
                    if level is None:
                        lines.append(t("profile_level_unknown",
                                       fallback="ℹ️ No se pudo leer el nivel (los showcases requieren nivel 10)"))
                        color = Colors.TEXT_SECONDARY
                    elif level >= 10:
                        lines.append(t("profile_level_ok", fallback="✅ Nivel {level}: puedes usar showcases",
                                       level=level))
                        color = Colors.SUCCESS
                    else:
                        lines.append(t("profile_level_low",
                                       fallback="⚠️ Nivel {level}: los showcases requieren nivel 10",
                                       level=level))
                        color = Colors.WARNING
                    show("\n".join(lines), color)
                except Exception as e:
                    show(f"❌ {e}", Colors.DANGER)

            threading.Thread(target=worker, daemon=True).start()

        ctk.CTkButton(dlg, text=t("validate_btn", fallback="Validar"), command=validate,
                      fg_color=Colors.ACCENT, height=34).pack(pady=8)

    # ------------------------------------------------------------------
    # ZIP export
    # ------------------------------------------------------------------
    def export_steam_pack(self):
        """Pack the current fragments plus upload instructions into a ZIP."""
        if not self._require_file():
            return
        fragments = self.processor.list_fragments(self.current_file)
        if not fragments:
            self._ui_warn(t("export_zip", fallback="Exportar ZIP"),
                          t("no_fragments_yet", fallback="Aún no hay fragmentos: usa el paso 3."))
            return
        preset = self.current_fragments_preset()
        readme = t("zip_readme", fallback=(
            "WorkshopArt - pack para Steam\n\n"
            "Formato: {preset}\nArchivos: {count}\n\n"
            "Cómo subirlos:\n"
            "1. Abre {url}\n"
            "2. Abre la consola del navegador (F12 -> Console), pega este código y pulsa Enter:\n\n"
            "{js}\n\n"
            "3. Sube cada archivo, ponle título y guarda (repite para cada parte).\n"
            "4. En tu perfil: Editar perfil -> Showcase -> asigna cada pieza a su hueco.\n\n"
            "Los showcases requieren una cuenta de Steam de nivel 10 o más.\n"),
            preset=self.preset_title(preset) if preset else "?", count=len(fragments),
            url=STEAM_UPLOAD_URL, js=self.steam_js_for_current())
        zip_path = fragments[0].parent / f"{self.current_file.stem}_steam_pack.zip"
        try:
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for fragment in fragments:
                    zf.write(fragment, fragment.name)
                zf.writestr("LEEME.txt", readme)
        except OSError as e:
            self._ui_error(t("export_zip", fallback="Exportar ZIP"), str(e))
            return
        self.log_message(f"Pack exportado: {zip_path}", "SUCCESS")
        self._ui_info(t("export_zip", fallback="Exportar ZIP"),
                      t("saved_in", fallback="Guardado en:\n{path}", path=zip_path))

"""ui.logic.upload - Steam upload helpers: Upload Tool launcher, JS snippets, auto-upload."""
import subprocess
import sys
import threading
from pathlib import Path
from tkinter import messagebox

from ui.logic.common import _NO_WINDOW_FLAGS


class UploadMixin:
    """Upload Tool subprocess launcher and cookie-based auto-upload."""

    def validate_steam_profile(self):
        """Stub: Steam profile validator — replaced by the PRO patch at module load."""
        messagebox.showinfo(
            "WorkshopArt PRO",
            "El validador de perfil Steam (nivel, showcases disponibles) es una "
            "funcion exclusiva de la version PRO.\n\n"
            "Descarga el .exe compilado en:\n"
            "https://mxteoo7.itch.io/workshopart-pro"
        )

    def export_steam_pack(self):
        """Stub: ZIP export of fragments + instructions — replaced by the PRO patch."""
        messagebox.showinfo(
            "WorkshopArt PRO",
            "El export ZIP (fragmentos + instrucciones listos para compartir) es una "
            "funcion exclusiva de la version PRO.\n\n"
            "Descarga el .exe compilado en:\n"
            "https://mxteoo7.itch.io/workshopart-pro"
        )

    def _launch_upload_tool(self, fragments=None, preset: str = None):
        """Launch the Upload Tool as a subprocess, passing fragment paths and preset as CLI args.

        In frozen (compiled) mode, re-invokes the same .exe with --upload-tool. In dev mode,
        looks for upload_tool.py two levels up; if absent, shows the PRO upgrade prompt.
        """
        try:
            flags = _NO_WINDOW_FLAGS
            extra = []
            if fragments:
                extra += ["--fragments"] + [str(f) for f in fragments]
            if preset:
                extra += ["--preset", preset]
            if getattr(sys, 'frozen', False):
                # Running as a compiled .exe — pass a flag to the same binary.
                subprocess.Popen([sys.executable, "--upload-tool"] + extra, **flags)
            else:
                upload_tool_path = Path(__file__).parent.parent / "upload_tool.py"
                if not upload_tool_path.exists():
                    # upload_tool.py is not included in the public repo — show upgrade prompt.
                    messagebox.showinfo(
                        "WorkshopArt PRO",
                        "El Upload Tool automatico es una funcion exclusiva de la version PRO.\n\n"
                        "Descarga el .exe compilado en:\n"
                        "https://mxteoo7.itch.io/workshopart-pro\n\n"
                        "La version gratuita incluye todos los presets y procesamiento IA.\n"
                        "Puedes subir los fragmentos manualmente siguiendo las instrucciones del README."
                    )
                    return
                subprocess.Popen([sys.executable, str(upload_tool_path)] + extra,
                                 cwd=str(upload_tool_path.parent), **flags)
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo abrir el Upload Tool:\n{e}")


    STEAM_JS_SNIPPET = (
        "$J('[name=consumer_app_id]').val(480);\n"
        "$J('[name=file_type]').val(0);\n"
        "$J('[name=visibility]').val(0);"
    )

    def _copy_steam_js(self):
        """Copiar snippet JS de Steam al portapapeles."""
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(self.STEAM_JS_SNIPPET)
            self.root.update()
            self.log_message("Snippet JS copiado al portapapeles", "SUCCESS")
            self._ui_info("Copiado", "Snippet JS copiado al portapapeles.\nPégalo en la consola del navegador (F12).")
        except Exception as e:
            self._ui_error("Error", f"No se pudo copiar: {e}")


    def _auto_upload_selected(self, parent_win):
        """Upload the checked fragments to Steam Workshop using the private steam_uploader module.

        steam_uploader.py and steam_cookies.json are gitignored (personal/PRO only). Shows an
        informative warning if the module or cookies are missing. Upload runs in a daemon thread
        with progress dispatched through update_queue.
        """
        # Lazy import: this is a private module not shipped in the public repo.
        try:
            import steam_uploader
        except ImportError:
            self._ui_warn(
                "Auto-upload no disponible",
                "El módulo privado 'steam_uploader' no está instalado.\n\n"
                "Para habilitarlo, coloca src/steam_uploader.py y steam_cookies.json "
                "(ambos gitignoreados)."
            )
            return

        if not steam_uploader.cookies_configured():
            self._ui_warn(
                "Cookies no disponibles",
                "El uploader necesita cookies de Steam. Opciones:\n\n"
                "1) Instala browser_cookie3 (pip install browser_cookie3) y loguéate en "
                "Steam desde Firefox. Cierra Firefox antes de subir.\n\n"
                "2) O crea 'steam_cookies.json' en la raíz con las claves "
                "sessionid y steamLoginSecure (F12 en steamcommunity.com → "
                "Application → Cookies)."
            )
            return
        src = steam_uploader.cookies_source()
        self.log_message(f"Fuente de cookies Steam: {src}", "INFO")

        selected = [info['path'] for part, (var, info) in self._fragment_checkboxes.items() if var.get()]
        if not selected:
            self._ui_warn("Nada que subir", "No has marcado ningún fragmento.")
            return

        if not messagebox.askyesno("Confirmar auto-upload",
                                   f"Se subirán {len(selected)} fragmentos a Steam Workshop.\n\n¿Continuar?"):
            return

        def worker():
            def progress(i, total, msg):
                # Dispatch both log and status updates via update_queue (worker -> main thread).
                self.update_queue.put((self.log_message, (f"[Upload {i}/{total}] {msg}", "INFO")))
                self.update_queue.put((self.update_status, (f"Subiendo {i}/{total}...", int(i*100/total), "🚀")))
            try:
                results = steam_uploader.upload_fragments(selected, progress_cb=progress)
                ok = sum(1 for _, b, _ in results if b)
                fail = len(results) - ok
                summary = f"Subidos: {ok}/{len(results)}\n\n"
                for path, good, msg in results:
                    summary += f"{'✅' if good else '❌'} {path.name}: {msg}\n"
                if fail == 0:
                    self._ui_info("Auto-upload completado", summary)
                else:
                    self._ui_error("Auto-upload con errores", summary)
            except Exception as e:
                self._ui_error("Error en auto-upload", str(e))

        threading.Thread(target=worker, daemon=True).start()



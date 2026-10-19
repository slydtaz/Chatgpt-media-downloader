"""Robust entry point for the single-file ChatGPT Media Downloader executable.

Keep this module deliberately small and import the application bootstrap *inside*
main(). That lets us record and display import-time/startup exceptions even when
the final Windows EXE is built without a console.
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
import traceback
from pathlib import Path

APP_TITLE = "ChatGPT Media Downloader — erro de inicialização"
FALLBACK_LOG_NAME = "startup-fallback.log"


def _startup_log_paths() -> list[Path]:
    """Return preferred and fallback log locations without touching the disk."""
    paths: list[Path] = []
    local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
    if local_app_data:
        paths.append(
            Path(local_app_data)
            / "ChatGPT"
            / "MediaDownloader"
            / "logs"
            / FALLBACK_LOG_NAME
        )

    # TEMP is normally present on Windows. tempfile.gettempdir() is a secondary
    # fallback for unusual environments where LOCALAPPDATA is not writable.
    temp_dir = os.environ.get("TEMP", "").strip()
    if temp_dir:
        paths.append(Path(temp_dir) / "ChatGPTMediaDownloader-startup.log")
    try:
        paths.append(Path(tempfile.gettempdir()) / "ChatGPTMediaDownloader-startup.log")
    except Exception:
        pass

    unique: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = str(path).casefold()
        if key not in seen:
            seen.add(key)
            unique.append(path)
    return unique


def _write_startup_log(message: str) -> Path | None:
    """Append a diagnostic line to the first writable per-user/temp log."""
    try:
        candidates = _startup_log_paths()
    except Exception:
        candidates = []

    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    entry = f"[{timestamp}] {message.rstrip()}\n"
    for path in candidates:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(entry)
            return path
        except Exception:
            # Continue to TEMP if the preferred per-user folder is not writable.
            continue
    return None


def _show_startup_error(message: str) -> None:
    """Show an error without relying on Tkinter or a console on Windows."""
    if os.name == "nt":
        try:
            import ctypes

            # MB_ICONERROR | MB_TOPMOST; works even if Tk initialization failed.
            ctypes.windll.user32.MessageBoxW(None, message, APP_TITLE, 0x10 | 0x00040000)
            return
        except Exception:
            pass

    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        try:
            messagebox.showerror(APP_TITLE, message, parent=root)
        finally:
            root.destroy()
        return
    except Exception:
        pass

    try:
        sys.stderr.write(message + "\n")
        sys.stderr.flush()
    except Exception:
        pass



def _run_gui_smoke_test() -> int:
    """Build the real GUI, render the orbit canvas and visit every page without downloads."""
    original_local_app_data = os.environ.get("LOCALAPPDATA")
    refresh_original = None
    update_check_original = None
    root = None
    failure: str | None = None
    visited: list[str] = []
    drawn_items = 0
    try:
        # Keep this smoke test completely isolated from the user's settings and tools.
        # Use a unique temporary profile. The CI runner discards TEMP when the job ends.
        # Do not delete it while a FileHandler may still have app.log open on Windows.
        isolated_data = tempfile.mkdtemp(prefix="cgmd-gui-smoke-")
        os.environ["LOCALAPPDATA"] = isolated_data
        os.environ["LOCALAPPDATA"] = isolated_data
        import time
        import tkinter as tk
        from app.gui import MediaDownloaderApp

        # The smoke test must never inspect, install or download media tools and
        # must never query GitHub for updates. Those flows are unrelated to GUI render.
        refresh_original = MediaDownloaderApp._refresh_dependencies
        update_check_original = MediaDownloaderApp._maybe_start_update_check
        MediaDownloaderApp._refresh_dependencies = lambda self, force=False: None
        MediaDownloaderApp._maybe_start_update_check = lambda self: None

        root = tk.Tk()
        root.geometry("1220x820")
        app = MediaDownloaderApp(root)
        root.update_idletasks()
        root.deiconify()
        root.update_idletasks()
        root.update()

        app._animate_hero_visual()
        drawn_items = len(app.hero_visual.find_all())
        if drawn_items < 12:
            raise RuntimeError(
                f"A animação do painel inicial desenhou apenas {drawn_items} elementos; esperado pelo menos 12."
            )

        for page_name in ("playlist", "settings", "dependencies", "updates", "help", "developer", "home"):
            app.show_page(page_name)
            # Wait for actual transition completion rather than assuming a 190 ms frame budget.
            deadline = time.monotonic() + 3.0
            while (app._visible_page != page_name or app._page_animation_job is not None) and time.monotonic() < deadline:
                root.update()
                time.sleep(0.01)
            root.update_idletasks()
            if app.current_page != page_name or app._visible_page != page_name or app._page_animation_job is not None:
                raise RuntimeError(f"A navegação não concluiu a transição para {page_name!r} em 3 segundos.")
            visited.append(page_name)

        root.destroy()
        root = None
    except Exception:
        failure = traceback.format_exc()
    finally:
        if root is not None:
            try:
                root.destroy()
            except Exception:
                pass
        try:
            from app.gui import MediaDownloaderApp
            if refresh_original is not None:
                MediaDownloaderApp._refresh_dependencies = refresh_original
            if update_check_original is not None:
                MediaDownloaderApp._maybe_start_update_check = update_check_original
        except Exception:
            pass
        if original_local_app_data is None:
            os.environ.pop("LOCALAPPDATA", None)
        else:
            os.environ["LOCALAPPDATA"] = original_local_app_data

    smoke_report = (
        "GUI SMOKE TEST FALHOU\\n" + failure
        if failure
        else "GUI SMOKE TEST OK\\n"
        + f"Elementos desenhados na animação: {drawn_items}\\n"
        + "Páginas percorridas: " + ", ".join(visited)
        + "\\nSem downloads de mídia nem verificações de atualização.\\n"
    )
    smoke_path = os.environ.get("CGMD_SMOKE_LOG", "").strip()
    if smoke_path:
        try:
            output_path = Path(smoke_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(smoke_report, encoding="utf-8")
        except OSError as exc:
            _write_startup_log(f"Não foi possível gravar o relatório do smoke test: {exc}")

    if failure:
        _write_startup_log("GUI SMOKE TEST FALHOU.\\n" + failure)
        try:
            sys.stderr.write(failure + "\\n")
            sys.stderr.flush()
        except Exception:
            pass
        return 1

    _write_startup_log(
        "GUI SMOKE TEST OK: janela real criada; órbitas desenhadas; páginas navegadas sem downloads."
    )
    return 0

def main(bootstrap_main=None) -> int:
    """Run the application, isolated GUI smoke test, or startup diagnostics."""
    if "--smoke-test-gui" in sys.argv[1:]:
        return _run_gui_smoke_test()
    _write_startup_log("ENTRYPOINT: início do executável.")
    try:
        if bootstrap_main is None:
            from app.bootstrap import main as bootstrap_main

        _write_startup_log("ENTRYPOINT: módulo de inicialização carregado; chamando bootstrap.")
        bootstrap_main()
    except Exception as exc:
        details = traceback.format_exc()
        log_path = _write_startup_log(
            "ERRO NÃO TRATADO durante a inicialização.\n" + details
        )
        log_location = str(log_path) if log_path else (
            "Não foi possível gravar o log nas pastas de dados nem em TEMP."
        )
        message = (
            "O ChatGPT Media Downloader não conseguiu iniciar.\n\n"
            f"Erro: {exc}\n\n"
            f"Diagnóstico: {log_location}\n\n"
            "Envie esse log para investigar a falha. Nenhum arquivo pessoal foi enviado."
        )
        try:
            _show_startup_error(message)
        except Exception:
            # Error reporting must never mask the original startup failure.
            pass
        return 1

    _write_startup_log("ENTRYPOINT: o bootstrap retornou normalmente.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

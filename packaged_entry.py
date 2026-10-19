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


def main(bootstrap_main=None) -> int:
    """Run the real bootstrap and report any exception that escapes it.

    The optional callable is a test seam; production runs import the bootstrap
    lazily so even an import error is captured by this function.
    """
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

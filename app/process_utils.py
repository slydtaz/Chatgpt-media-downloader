"""Helpers for launching subprocesses without spawning visible console windows on Windows."""
from __future__ import annotations

import os
import subprocess
from typing import Any, Iterable


def hidden_subprocess_kwargs(platform_name: str | None = None) -> dict[str, Any]:
    """Return platform-specific flags that suppress child console windows.

    `platform_name` is injectable for unit tests. On non-Windows systems the
    helper returns no extra flags so normal POSIX subprocess behavior is kept.
    """
    platform_name = platform_name or os.name
    if platform_name != "nt":
        return {}

    # CREATE_NO_WINDOW is 0x08000000 on Windows. The fallback keeps tests and
    # alternative Python builds robust if the symbolic constant is absent.
    kwargs: dict[str, Any] = {
        "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000),
    }
    startup_factory = getattr(subprocess, "STARTUPINFO", None)
    if startup_factory:
        startup = startup_factory()
        startup.dwFlags |= getattr(subprocess, "STARTF_USESHOWWINDOW", 1)
        startup.wShowWindow = getattr(subprocess, "SW_HIDE", 0)
        kwargs["startupinfo"] = startup
    return kwargs


def refresh_windows_shell_items(paths: Iterable[os.PathLike[str] | str], platform_name: str | None = None) -> int:
    """Notify Windows Explorer that media files changed, so its thumbnail cache can refresh.

    It does not install or replace a thumbnail provider and therefore cannot
    guarantee album-art thumbnails on Windows editions/configurations that do
    not render embedded MP3 artwork. Returns the number of paths notified.
    """
    platform_name = platform_name or os.name
    if platform_name != "nt":
        return 0
    try:
        import ctypes
        shell32 = ctypes.WinDLL("shell32", use_last_error=True)
        notify = shell32.SHChangeNotify
        notify.argtypes = [ctypes.c_long, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]
        notify.restype = None
        count = 0
        # SHCNE_UPDATEITEM = 0x00002000; SHCNF_PATHW = 0x0005
        for raw_path in paths:
            try:
                path = os.fspath(raw_path)
                if not os.path.isfile(path):
                    continue
                wide_path = ctypes.create_unicode_buffer(os.path.abspath(path))
                notify(0x00002000, 0x0005, ctypes.cast(wide_path, ctypes.c_void_p), None)
                count += 1
            except (OSError, TypeError, ValueError):
                continue
        return count
    except (AttributeError, OSError):
        return 0

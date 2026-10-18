from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path


def create_cleanup_script(app_data: Path, install_root: Path | None = None) -> Path:
    app_data_str = str(app_data)
    install_root_str = str(install_root) if install_root else ""
    script_dir = Path(tempfile.mkdtemp(prefix="cgm_uninstall_"))
    script = script_dir / ("cleanup.bat" if os.name == "nt" else "cleanup.sh")
    if os.name == "nt":
        content = f"""@echo off
set PID={os.getpid()}
:wait
tasklist /FI "PID eq %PID%" | findstr /R /C:" %PID% " >nul
if not errorlevel 1 (
  timeout /t 1 /nobreak >nul
  goto wait
)
rmdir /s /q "{app_data_str}" 2>nul
"""
        if install_root_str:
            content += f'rmdir /s /q "{install_root_str}" 2>nul\n'
        content += f'rmdir /s /q "{script_dir}" 2>nul\n'
    else:
        content = f"""#!/bin/sh
sleep 2
rm -rf -- "{app_data_str}"
"""
        if install_root_str:
            content += f'rm -rf -- "{install_root_str}"\n'
        content += f'rm -rf -- "{script_dir}"\n'
    script.write_text(content, encoding="utf-8")
    if os.name != "nt":
        script.chmod(0o700)
    return script


def launch_uninstaller(app_data: Path, install_root: Path | None = None) -> None:
    script = create_cleanup_script(app_data, install_root)
    if os.name == "nt":
        # Program Files normally requires elevation. Ask Windows for it only
        # when necessary; per-user installs do not need UAC.
        program_files = os.environ.get("ProgramW6432") or os.environ.get("ProgramFiles") or r"C:\Program Files"
        install_text = str(install_root).rstrip("\\/").lower() if install_root else ""
        pf_text = str(Path(program_files)).rstrip("\\/").lower()
        needs_elevation = bool(install_root and (install_text == pf_text or install_text.startswith(pf_text + os.sep.lower())))
        if needs_elevation:
            import ctypes
            params = f'/c ""{script}""'
            result = ctypes.windll.shell32.ShellExecuteW(None, "runas", "cmd.exe", params, None, 0)
            if result <= 32:
                raise OSError(f"O Windows não permitiu a elevação para desinstalar (código {result}).")
        else:
            subprocess.Popen(["cmd.exe", "/c", "start", "", str(script)], creationflags=subprocess.CREATE_NO_WINDOW)
    else:
        subprocess.Popen(["sh", str(script)], start_new_session=True)

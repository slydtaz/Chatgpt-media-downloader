from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

from .config import PRODUCT_ID, VENDOR


INSTALL_MARKER = ".chatgpt-media-downloader-install.json"


def _validated_paths(app_data: Path, install_root: Path | None) -> tuple[Path, Path | None]:
    """Validate deletion boundaries before scheduling cleanup."""
    data_path = app_data.expanduser().resolve()
    if data_path.name.casefold() != "mediadownloader" or data_path.parent.name.casefold() != "chatgpt":
        raise ValueError("A pasta de dados não parece pertencer ao ChatGPT Media Downloader.")

    owned_root = None
    if install_root is not None:
        candidate = install_root.expanduser().resolve()
        marker_path = candidate / INSTALL_MARKER
        try:
            marker = json.loads(marker_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("A pasta de instalação não tem um marcador de propriedade válido; ela não será apagada.") from exc
        if marker.get("vendor") != VENDOR or marker.get("product_id") != PRODUCT_ID:
            raise ValueError("O marcador da pasta não corresponde ao ChatGPT Media Downloader; ela não será apagada.")
        if candidate == candidate.parent or len(candidate.parts) < 3:
            raise ValueError("A pasta indicada é ampla demais para uma desinstalação segura.")
        owned_root = candidate
    return data_path, owned_root


def create_cleanup_script(app_data: Path, install_root: Path | None = None) -> Path:
    app_data, install_root = _validated_paths(app_data, install_root)
    process_id = os.getpid()
    script_dir = Path(tempfile.mkdtemp(prefix="cgm_uninstall_"))

    if os.name == "nt":
        script = script_dir / "cleanup.ps1"
        data_literal = str(app_data).replace("'", "''")
        install_literal = str(install_root or "").replace("'", "''")
        content = f"""$ErrorActionPreference = 'Stop'
$processId = {process_id}
$appData = '{data_literal}'
$installRoot = '{install_literal}'
while (Get-Process -Id $processId -ErrorAction SilentlyContinue) {{
    Start-Sleep -Seconds 1
}}
# Defensive check: only remove the known app-data directory shape.
if ([IO.Path]::GetFileName($appData) -ne 'MediaDownloader' -or
    [IO.Path]::GetFileName([IO.Path]::GetDirectoryName($appData)) -ne 'ChatGPT') {{
    throw 'Caminho de dados inesperado; limpeza cancelada.'
}}
if (Test-Path -LiteralPath $appData) {{
    Remove-Item -LiteralPath $appData -Recurse -Force
}}
if (-not [string]::IsNullOrWhiteSpace($installRoot)) {{
    $markerPath = Join-Path $installRoot '{INSTALL_MARKER}'
    if (Test-Path -LiteralPath $markerPath) {{
        $marker = Get-Content -LiteralPath $markerPath -Raw | ConvertFrom-Json
        if ($marker.vendor -eq '{VENDOR}' -and $marker.product_id -eq '{PRODUCT_ID}') {{
            Remove-Item -LiteralPath $installRoot -Recurse -Force
        }}
    }}
}}
# Delete the temporary helper after PowerShell has exited.
$cleanupDir = $PSScriptRoot
$cleanupCmd = 'timeout /t 2 /nobreak >nul & rmdir /s /q "' + $cleanupDir + '"'
Start-Process -FilePath $env:ComSpec -ArgumentList @('/d', '/c', $cleanupCmd) -WindowStyle Hidden
"""
        script.write_text(content, encoding="utf-8-sig")
    else:
        script = script_dir / "cleanup.sh"
        data_q = shlex.quote(str(app_data))
        root_q = shlex.quote(str(install_root)) if install_root else ""
        marker_q = shlex.quote(INSTALL_MARKER)
        vendor_q = shlex.quote(VENDOR)
        product_q = shlex.quote(PRODUCT_ID)
        removal = ""
        if install_root:
            removal = f"""if [ -f {root_q}/{marker_q} ]; then
  if grep -q {vendor_q} {root_q}/{marker_q} && grep -q {product_q} {root_q}/{marker_q}; then
    rm -rf -- {root_q}
  fi
fi
"""
        content = f"""#!/bin/sh
set -eu
process_id={process_id}
while kill -0 "$process_id" 2>/dev/null; do sleep 1; done
rm -rf -- {data_q}
{removal}
rm -f -- "$0"
rmdir -- "$(dirname "$0")" 2>/dev/null || true
"""
        script.write_text(content, encoding="utf-8")
        script.chmod(0o700)
    return script


def launch_uninstaller(app_data: Path, install_root: Path | None = None) -> None:
    """Schedule self-removal after exit; never deletes a folder without our marker."""
    script = create_cleanup_script(app_data, install_root)
    if os.name == "nt":
        program_files = (
            os.environ.get("ProgramW6432")
            or os.environ.get("ProgramFiles")
            or r"C:\\Program Files"
        )
        install_text = str(install_root.resolve()).rstrip("\\\\/").casefold() if install_root else ""
        pf_text = str(Path(program_files).resolve()).rstrip("\\\\/").casefold()
        needs_elevation = bool(
            install_root
            and (install_text == pf_text or install_text.startswith(pf_text + os.sep.casefold()))
        )
        if needs_elevation:
            import ctypes

            params = f'-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "{script}"'
            result = ctypes.windll.shell32.ShellExecuteW(None, "runas", "powershell.exe", params, None, 0)
            if result <= 32:
                script.unlink(missing_ok=True)
                raise OSError(f"O Windows não permitiu a elevação para desinstalar (código {result}).")
        else:
            subprocess.Popen(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(script)],
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                close_fds=True,
            )
    else:
        subprocess.Popen(["sh", str(script)], start_new_session=True)

from __future__ import annotations

import json
import os
import re
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Optional

from .config import (
    APP_DATA,
    INSTALL_ID_PATH,
    PRODUCT_ID,
    VENDOR,
    VERSION,
    ensure_dirs,
    ensure_install_id,
    load_config,
    save_installation_baseline,
)
from .dependencies import inspect_tool
from .locking import InstanceGuard, show_startup_notice
from .platform import detect_system
from .updater import UpdateError, install_tool_from_release


INSTALL_MARKER = ".chatgpt-media-downloader-install.json"
INSTALL_FOLDER_PREFIX = "MediaDownloader-com.chatgpt.mediadownloader-"


def current_project_root() -> Path:
    # In a PyInstaller one-file build, bundled modules live in a temporary
    # extraction folder. The executable itself is the distributable source.
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def _windows_program_files() -> Path:
    return Path(
        os.environ.get("ProgramW6432")
        or os.environ.get("ProgramFiles")
        or r"C:\\Program Files"
    )


def preferred_install_root(install_id: str, system) -> Path:
    folder = f"{INSTALL_FOLDER_PREFIX}{install_id[:12]}"
    if system.os_name == "Windows":
        return _windows_program_files() / "ChatGPT" / folder
    if system.os_name == "Darwin":
        return Path("/Applications") / f"ChatGPT Media Downloader-{install_id[:12]}"
    return Path("/opt") / folder


def per_user_install_root(install_id: str, system) -> Path:
    folder = f"{INSTALL_FOLDER_PREFIX}{install_id[:12]}"
    if system.os_name == "Windows":
        local = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
        return local / "Programs" / "ChatGPT" / folder
    if system.os_name == "Darwin":
        return Path.home() / "Applications" / folder
    return Path.home() / ".local" / "opt" / folder


def _marker_data(install_id: str, source: Path) -> dict:
    return {
        "vendor": VENDOR,
        "product_id": PRODUCT_ID,
        "version": VERSION,
        "install_id": install_id,
        "installed_from": str(source),
        "installed_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }


def _is_product_install(path: Path) -> bool:
    """Validate product ownership without requiring the current Install ID."""
    marker = path / INSTALL_MARKER
    if not marker.is_file():
        return False
    try:
        data = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return data.get("vendor") == VENDOR and data.get("product_id") == PRODUCT_ID


def _is_ours(path: Path, install_id: str) -> bool:
    if not _is_product_install(path):
        return False
    try:
        data = json.loads((path / INSTALL_MARKER).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return data.get("install_id") == install_id

def _version_key(value: object) -> tuple[int, ...]:
    """Compare dotted app versions numerically without requiring packaging."""
    match = re.search(r"v?(\d+(?:\.\d+){0,5})", str(value or "").strip(), re.IGNORECASE)
    if not match:
        return (0,)
    try:
        return tuple(int(part) for part in match.group(1).split("."))
    except ValueError:
        return (0,)


def _version_is_newer(candidate: object, current: object) -> bool:
    left, right = _version_key(candidate), _version_key(current)
    width = max(len(left), len(right))
    return left + (0,) * (width - len(left)) > right + (0,) * (width - len(right))


def _installed_version(path: Path, install_id: str) -> str:
    """Read a version only from an installation owned by this product and ID."""
    if not _is_ours(path, install_id):
        return ""
    try:
        data = json.loads((path / INSTALL_MARKER).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    return str(data.get("version") or "")


def _newest_install_not_older(candidates: list[Path], install_id: str, source_version: str) -> Path | None:
    """Find an existing owned copy newer than the launcher being started.

    Older shortcuts and downloaded portable copies must never overwrite a newer
    installation merely because the user opened the old entry point again.
    """
    versions = [(candidate, _installed_version(candidate, install_id)) for candidate in candidates]
    newer = [(candidate, version) for candidate, version in versions if version and _version_is_newer(version, source_version)]
    if not newer:
        return None
    return max(newer, key=lambda item: _version_key(item[1]))[0]


def sync_portable_entrypoint(install_root: Path, install_id: str, running_executable: Path | None = None) -> bool:
    """Refresh the original portable EXE so reopening it cannot roll back an update."""
    if not _is_ours(install_root, install_id):
        return False
    try:
        marker_path = install_root / INSTALL_MARKER
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
        origin_text = str(marker.get("installed_from") or "").strip()
        if not origin_text:
            return False
        origin = Path(origin_text).expanduser().resolve()
        current = Path(running_executable or sys.executable).expanduser().resolve()
        if origin == current or origin.parent == current.parent:
            return False
        expected_name = "ChatGPTMediaDownloader.exe" if current.suffix.lower() == ".exe" else current.name
        if origin.name.lower() != expected_name.lower() or not origin.is_file() or not current.is_file():
            return False
        if origin.stat().st_size == current.stat().st_size and _sha256_file(origin) == _sha256_file(current):
            return False

        staged = origin.with_name(f".{origin.name}.{uuid.uuid4().hex[:10]}.new")
        try:
            shutil.copy2(current, staged)
            if staged.stat().st_size != current.stat().st_size or _sha256_file(staged) != _sha256_file(current):
                raise RuntimeError("A entrada portátil não passou na verificação SHA-256.")
            os.replace(staged, origin)
            if origin.stat().st_size != current.stat().st_size or _sha256_file(origin) != _sha256_file(current):
                raise RuntimeError("A entrada portátil substituída não corresponde ao executável instalado.")
        finally:
            staged.unlink(missing_ok=True)

        marker["portable_entrypoint_synced_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        marker["portable_entrypoint_sha256"] = _sha256_file(current)
        temp_marker = marker_path.with_name(f".{marker_path.name}.{uuid.uuid4().hex[:8]}.tmp")
        try:
            temp_marker.write_text(json.dumps(marker, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            os.replace(temp_marker, marker_path)
        finally:
            temp_marker.unlink(missing_ok=True)
        return True
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError):
        # The installed EXE remains usable even if the original portable path is read-only.
        return False



def _remove_directory_contents(path: Path) -> None:
    """Remove only the contents of an already-identified application directory."""
    for child in list(path.iterdir()):
        try:
            if child.is_dir() and not child.is_symlink():
                shutil.rmtree(child)
            else:
                child.unlink()
        except FileNotFoundError:
            continue


def _copy_project_tree(source: Path, destination: Path, install_id: str) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    ignored_names = {"__pycache__", ".pytest_cache", ".git", INSTALL_MARKER, ".installing", ".extracting"}

    # A destination is wiped only after its ownership has been positively
    # identified through our vendor/product/Install-ID marker. This prevents
    # accidentally deleting another application from Program Files.
    if _is_ours(destination, install_id):
        _remove_directory_contents(destination)

    for item in source.iterdir():
        if item.name in ignored_names or item.name == INSTALL_MARKER:
            continue
        target = destination / item.name
        if item.is_dir():
            shutil.copytree(
                item,
                target,
                dirs_exist_ok=True,
                ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", ".git", ".installing", ".extracting"),
            )
        elif item.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)

    (destination / INSTALL_MARKER).write_text(
        json.dumps(_marker_data(install_id, source), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _validate_staged_install(path: Path, install_id: str) -> None:
    """Refuse to switch an installation to a partial or malformed source tree."""
    required = (
        path / "app" / "main.py",
        path / "app" / "bootstrap.py",
        path / "launcher.vbs",
        path / "launcher.sh",
        path / "PROJECT_ID",
        path / INSTALL_MARKER,
    )
    missing = [str(item.name) for item in required if not item.is_file()]
    if missing:
        raise RuntimeError("Pacote incompleto; faltam arquivos: " + ", ".join(missing))
    if not _is_ours(path, install_id):
        raise RuntimeError("O marcador da instalação preparada não corresponde ao Install ID atual.")
    if (path / "PROJECT_ID").read_text(encoding="utf-8", errors="replace").strip() != PRODUCT_ID:
        raise RuntimeError("O Product ID do pacote preparado não corresponde ao aplicativo.")


def _transactional_install_copy(source: Path, destination: Path, install_id: str) -> None:
    """Stage and validate first; swap with rollback so a failed update keeps the old app."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex[:10]
    stage = destination.with_name(f"{destination.name}.staging-{token}")
    # Keep the backup name discoverable as an owned product folder if Windows
    # temporarily prevents its removal because a previous process is still open.
    backup = destination.with_name(f"{destination.name}.backup-{token}")
    try:
        _copy_project_tree(source, stage, install_id)
        _validate_staged_install(stage, install_id)

        if destination.exists():
            if not _is_product_install(destination):
                raise RuntimeError(f"Destino existente não foi identificado como instalação deste produto: {destination}")
            os.replace(destination, backup)
        try:
            os.replace(stage, destination)
        except OSError:
            if backup.exists() and not destination.exists():
                os.replace(backup, destination)
            raise
        if backup.exists():
            try:
                shutil.rmtree(backup)
            except (OSError, shutil.Error):
                # The new install is already valid. A later launch may clean an
                # owned backup if a running process currently holds old files.
                pass
    finally:
        if stage.exists():
            shutil.rmtree(stage, ignore_errors=True)


def _owned_install_candidates(system) -> list[Path]:
    """Find old installations belonging to this product, never arbitrary Program Files folders."""
    candidates: list[Path] = []
    if system.os_name == "Windows":
        local = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
        roots = [
            _windows_program_files() / "ChatGPT",
            Path(os.environ.get("ProgramW6432") or r"C:\Program Files") / "ChatGPT",
            Path(os.environ.get("ProgramFiles(x86)") or r"C:\Program Files (x86)") / "ChatGPT",
            local / "Programs" / "ChatGPT",
        ]
    elif system.os_name == "Darwin":
        roots = [Path("/Applications"), Path.home() / "Applications"]
    elif system.os_name == "Linux":
        roots = [Path("/opt"), Path.home() / ".local" / "opt"]
    else:
        roots = []

    seen: set[str] = set()
    for root in roots:
        try:
            if not root.is_dir():
                continue
            for candidate in root.iterdir():
                if not candidate.is_dir():
                    continue
                expected_name = candidate.name.startswith(INSTALL_FOLDER_PREFIX)
                if system.os_name == "Darwin":
                    expected_name = expected_name or candidate.name.startswith("ChatGPT Media Downloader-")
                if expected_name and _is_product_install(candidate):
                    key = str(candidate.resolve())
                    if key not in seen:
                        seen.add(key)
                        candidates.append(candidate)
        except OSError:
            continue
    return candidates


def remove_old_owned_installations(*, keep: Path | None = None, source: Path | None = None, system=None) -> list[Path]:
    """Remove older copies in system application locations, but only ours.

    A source directory is excluded so launching a fresh ZIP never deletes the
    copy currently being used to perform the upgrade. A keep path can also be
    supplied for a destination that must remain in place.
    """
    system = system or detect_system()
    keep_resolved = None
    source_resolved = None
    try:
        keep_resolved = keep.resolve() if keep else None
    except OSError:
        pass
    try:
        source_resolved = source.resolve() if source else None
    except OSError:
        pass

    removed: list[Path] = []
    for candidate in _owned_install_candidates(system):
        try:
            resolved = candidate.resolve()
        except OSError:
            resolved = candidate
        if resolved in {p for p in (keep_resolved, source_resolved) if p is not None}:
            continue
        try:
            shutil.rmtree(candidate)
            removed.append(candidate)
        except (OSError, shutil.Error):
            # Do not escalate to a dangerous fallback. A locked owned install
            # is left intact and handled by the normal copy/user-install path.
            continue
    return removed

def _sha256_file(path: Path) -> str:
    import hashlib
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _transactional_install_executable(source_exe: Path, destination: Path, install_id: str) -> None:
    """Install the single-file build as one executable plus an ownership marker."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex[:10]
    stage = destination.with_name(f"{destination.name}.staging-{token}")
    backup = destination.with_name(f"{destination.name}.backup-{token}")
    exe_name = "ChatGPTMediaDownloader.exe" if os.name == "nt" else "ChatGPTMediaDownloader"
    try:
        stage.mkdir(parents=True, exist_ok=False)
        staged_exe = stage / exe_name
        shutil.copy2(source_exe, staged_exe)
        if not staged_exe.is_file() or staged_exe.stat().st_size != source_exe.stat().st_size:
            raise RuntimeError("O executável copiado está incompleto.")
        if _sha256_file(staged_exe) != _sha256_file(source_exe):
            raise RuntimeError("A verificação SHA-256 do executável copiado falhou.")
        (stage / INSTALL_MARKER).write_text(
            json.dumps(_marker_data(install_id, source_exe), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        marker_data = json.loads((stage / INSTALL_MARKER).read_text(encoding="utf-8"))
        if (marker_data.get("vendor") != VENDOR or marker_data.get("product_id") != PRODUCT_ID
                or marker_data.get("install_id") != install_id):
            raise RuntimeError("O marcador da instalação preparada não passou na validação.")

        if destination.exists():
            if not _is_product_install(destination):
                raise RuntimeError(f"O destino existente não pertence a este produto: {destination}")
            os.replace(destination, backup)
        try:
            os.replace(stage, destination)
        except OSError:
            if backup.exists() and not destination.exists():
                os.replace(backup, destination)
            raise
        if backup.exists():
            try:
                shutil.rmtree(backup)
            except (OSError, shutil.Error):
                pass
    finally:
        if stage.exists():
            shutil.rmtree(stage, ignore_errors=True)


def _directory_is_writable(path: Path) -> bool:
    """Check whether the current user can replace files in an existing install folder."""
    if not path.is_dir():
        return False
    probe = path / f".cgm-write-check-{uuid.uuid4().hex}"
    try:
        with probe.open("xb") as handle:
            handle.write(b"ok")
        return True
    except OSError:
        return False
    finally:
        try:
            probe.unlink(missing_ok=True)
        except OSError:
            pass


def ensure_frozen_installation(source_exe: Path, install_id: str, system) -> tuple[Path, bool]:
    """Self-install a PyInstaller one-file executable without a source project tree."""
    preferred = preferred_install_root(install_id, system)
    user = per_user_install_root(install_id, system)
    resolved_exe = source_exe.resolve()

    # Prefer a per-user installation on Windows. It can be repaired and updated
    # without requiring admin rights to replace an EXE under Program Files.
    candidates = (user, preferred) if system.os_name == "Windows" else (preferred, user)
    for candidate in candidates:
        try:
            if resolved_exe.parent == candidate.resolve() and _is_ours(candidate, install_id):
                if candidate == user or _directory_is_writable(candidate):
                    return candidate, False
                # A non-elevated process cannot safely update this system install.
                # Reinstall into the user profile and use that copy going forward.
                break
        except OSError:
            continue

    # A stale portable EXE must never downgrade a newer owned installation.
    newer_install = _newest_install_not_older([preferred, user], install_id, VERSION)
    if newer_install is not None:
        return newer_install, True

    errors: list[str] = []
    for candidate in candidates:
        try:
            candidate.parent.mkdir(parents=True, exist_ok=True)
            if candidate.exists() and not _is_product_install(candidate):
                raise RuntimeError(f"Destino existente não pertence ao ChatGPT Media Downloader: {candidate}")
            _transactional_install_executable(source_exe, candidate, install_id)
            remove_old_owned_installations(keep=candidate, system=system)
            return candidate, True
        except (OSError, shutil.Error, RuntimeError) as exc:
            errors.append(f"{candidate}: {exc}")
    raise RuntimeError("Não foi possível instalar o executável. Tentativas: " + " | ".join(errors))


def ensure_installation(source: Path, install_id: str, system) -> tuple[Path, bool]:
    # When already running from our own install path, do not copy over a live
    # executable tree. A newer package extracted elsewhere will perform a staged swap.
    preferred = preferred_install_root(install_id, system)
    user = per_user_install_root(install_id, system)
    resolved_source = source.resolve()

    for candidate in (preferred, user):
        try:
            if resolved_source == candidate.resolve() and _is_ours(candidate, install_id):
                return candidate, False
        except OSError:
            pass

    # A stale extracted source package must never downgrade an installed version.
    newer_install = _newest_install_not_older([preferred, user], install_id, VERSION)
    if newer_install is not None:
        return newer_install, True

    errors: list[str] = []
    for candidate in (preferred, user):
        try:
            candidate.parent.mkdir(parents=True, exist_ok=True)
            if candidate.exists() and not _is_product_install(candidate):
                raise RuntimeError(f"Destino existente não pertence ao ChatGPT Media Downloader: {candidate}")
            _transactional_install_copy(source, candidate, install_id)
            # Only after a complete, validated install is in place do we remove
            # other old copies, and only if their product marker matches.
            remove_old_owned_installations(keep=candidate, source=source, system=system)
            return candidate, True
        except (OSError, shutil.Error, RuntimeError) as exc:
            errors.append(f"{candidate}: {exc}")
            continue
    raise RuntimeError("Não foi possível instalar a aplicação. Tentativas: " + " | ".join(errors))

def _pythonw_executable() -> str:
    current = Path(sys.executable)
    if os.name == "nt":
        candidate = current.with_name("pythonw.exe")
        if candidate.is_file():
            return str(candidate)
        # Fall back to a PATH-resolved pythonw before python. This keeps the
        # application console-free when possible.
        where = shutil.which("pythonw.exe") or shutil.which("pythonw")
        if where:
            return where
    return str(current)


def _hidden_popen(args: list[str], *, cwd: Optional[Path] = None) -> subprocess.Popen:
    kwargs = {"cwd": str(cwd) if cwd else None, "close_fds": True}
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = 0
        kwargs["startupinfo"] = startup
    return subprocess.Popen(args, **kwargs)


def relaunch_from_install(install_root: Path, handoff_token: str) -> subprocess.Popen:
    if getattr(sys, "frozen", False):
        exe_name = "ChatGPTMediaDownloader.exe" if os.name == "nt" else "ChatGPTMediaDownloader"
        target = install_root / exe_name
        args = [str(target), "--installed", f"--handoff-token={handoff_token}"]
    else:
        pythonw = _pythonw_executable()
        args = [pythonw, "-m", "app.bootstrap", "--installed", f"--handoff-token={handoff_token}"]
    return _hidden_popen(args, cwd=install_root)


def _vbs_string(value: str) -> str:
    return '"' + str(value).replace('"', '""') + '"'


def create_desktop_shortcut(install_root: Path) -> Optional[Path]:
    if os.name != "nt":
        return None

    temp_dir = Path(tempfile.mkdtemp(prefix="cgm_shortcut_"))
    try:
        probe = temp_dir / "desktop_probe.vbs"
        probe.write_text(
            'Set sh = CreateObject("WScript.Shell")\n'
            'WScript.StdOut.Write sh.SpecialFolders("Desktop")\n',
            encoding="utf-8",
        )
        completed = subprocess.run(
            ["cscript.exe", "//nologo", str(probe)],
            capture_output=True, text=True, timeout=10, check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        desktop_text = (completed.stdout or "").strip()
        desktop = Path(desktop_text) if desktop_text else Path.home() / "Desktop"
        desktop.mkdir(parents=True, exist_ok=True)
        shortcut = desktop / "ChatGPT Media Downloader.lnk"
        installed_exe = install_root / "ChatGPTMediaDownloader.exe"
        vbs = install_root / "launcher.vbs"
        if installed_exe.is_file():
            target_path = installed_exe
            arguments = ""
        elif vbs.is_file():
            target_path = Path(os.environ.get("SystemRoot") or r"C:\Windows") / "System32" / "wscript.exe"
            arguments = '//nologo "' + str(vbs) + '"'
        else:
            return None

        script = temp_dir / "create_shortcut.vbs"
        script.write_text(
            'Set sh = CreateObject("WScript.Shell")\n'
            f'Set sc = sh.CreateShortcut({_vbs_string(str(shortcut))})\n'
            f'Sc.TargetPath = {_vbs_string(str(target_path))}\n'
            f'Sc.Arguments = {_vbs_string(arguments)}\n'
            f'Sc.WorkingDirectory = {_vbs_string(str(install_root))}\n'
            'sc.Description = "ChatGPT Media Downloader"\n'
            'sc.IconLocation = "%SystemRoot%\\System32\\shell32.dll,167"\n'
            'sc.Save\n',
            encoding="utf-8",
        )
        _hidden_popen(["wscript.exe", "//nologo", str(script)], cwd=temp_dir).wait(timeout=15)
        return shortcut if shortcut.is_file() else None
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

def create_linux_desktop_entry(install_root: Path) -> Optional[Path]:
    if detect_system().os_name != "Linux":
        return None
    applications = Path(os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share")) / "applications"
    applications.mkdir(parents=True, exist_ok=True)
    desktop = applications / "chatgpt-media-downloader.desktop"
    installed_binary = install_root / "ChatGPTMediaDownloader"
    if installed_binary.is_file():
        command = f'"{installed_binary}" --installed'
    else:
        python = shutil.which("python3") or shutil.which("python")
        if not python:
            return None
        command = f'"{python}" -m app.bootstrap --installed'
    content = (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=ChatGPT Media Downloader\n"
        "Comment=Downloader gráfico de mídia\n"
        f"Exec={command}\n"
        f"Path={install_root}\n"
        "Terminal=false\n"
        "Categories=AudioVideo;Network;\n"
    )
    desktop.write_text(content, encoding="utf-8")
    desktop.chmod(0o644)
    return desktop

def schedule_source_cleanup(source: Path, install_root: Path) -> None:
    try:
        if source.resolve() == install_root.resolve():
            return
    except OSError:
        return
    marker_candidates = [source / "PROJECT_ID", source / "docs" / "ChatGPT_Media_Downloader_3.9-BAT_reference.bat", source / "launcher.bat"]
    if not all(p.exists() for p in marker_candidates):
        return
    try:
        if (source / "PROJECT_ID").read_text(encoding="utf-8").strip() != PRODUCT_ID:
            return
    except OSError:
        return
    temp_dir = Path(tempfile.mkdtemp(prefix="cgm_cleanup_"))
    script = temp_dir / "cleanup.vbs"
    script.write_text(
        "Set fso = CreateObject(\"Scripting.FileSystemObject\")\n"
        "WScript.Sleep 2500\n"
        f"Set f = fso.GetFolder({_vbs_string(str(source))})\n"
        "On Error Resume Next\n"
        "fso.DeleteFolder f.Path, True\n"
        "WScript.Quit\n",
        encoding="utf-8",
    )
    _hidden_popen(["wscript.exe", "//nologo", str(script)], cwd=temp_dir)


def _dependency_ready(system) -> bool:
    from .config import load_config

    config = load_config()
    infos = {
        name: inspect_tool(name, config.get(f"{name.replace('-', '_')}_path", ""), system)
        for name in ("yt-dlp", "ffmpeg", "ffprobe")
    }
    return all(info.path and info.executable_ok and not info.error for info in infos.values())


def _dependency_paths(system):
    from .config import load_config

    config = load_config()
    result = {}
    for name, key in (("yt-dlp", "yt_dlp_path"), ("ffmpeg", "ffmpeg_path"), ("ffprobe", "ffprobe_path")):
        result[name] = inspect_tool(name, config.get(key, ""), system)
    return result


class BootstrapUI:
    """Responsive splash window; all dependency work runs away from Tk's UI thread."""
    def __init__(self):
        import tkinter as tk
        from tkinter import ttk

        self.tk = tk
        self.root = tk.Tk()
        self.root.title("ChatGPT Media Downloader")
        self.root.geometry("520x190")
        self.root.resizable(False, False)
        self.root.configure(bg="#111827")
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TFrame", background="#111827")
        style.configure("TLabel", background="#111827", foreground="#F8FAFC")
        style.configure("Muted.TLabel", background="#111827", foreground="#CBD5E1")
        style.configure("TProgressbar", thickness=10)
        frame = ttk.Frame(self.root, padding=24)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="CHATGPT MEDIA DOWNLOADER", font=("Segoe UI", 15, "bold")).pack(anchor="w")
        self.label = ttk.Label(frame, text="Verificando dependências...", style="Muted.TLabel")
        self.label.pack(anchor="w", pady=(7, 10))
        self.progress = ttk.Progressbar(frame, maximum=100, mode="determinate")
        self.progress.pack(fill="x")
        self.detail = ttk.Label(frame, text="", style="Muted.TLabel")
        self.detail.pack(anchor="w", pady=(7, 0))
        self.events: queue.Queue = queue.Queue()
        self._task_result = None
        self._task_error: BaseException | None = None
        self.root.protocol("WM_DELETE_WINDOW", lambda: None)
        self.root.after(60, self._pump)

    def update(self, label: str, detail: str = "", percent: Optional[float] = None):
        # Safe from installer worker threads: only enqueue data; Tk is touched by _pump.
        self.events.put(("update", (label, detail, percent)))

    def _apply_update(self, label: str, detail: str = "", percent: Optional[float] = None):
        try:
            self.label.configure(text=label)
            self.detail.configure(text=detail)
            if percent is not None:
                self.progress.configure(value=max(0, min(100, percent)))
        except self.tk.TclError:
            pass

    def _pump(self):
        # Coalesce progress events: large downloads may emit one event per MiB.
        # Rendering only the newest state keeps Tk responsive on slower PCs.
        latest_update = None
        task_done = None
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "update":
                    latest_update = payload
                elif kind == "task_done":
                    task_done = payload
        except queue.Empty:
            pass
        if latest_update is not None:
            self._apply_update(*latest_update)
        if task_done is not None:
            success, value = task_done
            if success:
                self._task_result = value
            else:
                self._task_error = value
            try:
                self.root.quit()
            except self.tk.TclError:
                pass
            return
        try:
            self.root.after(60, self._pump)
        except self.tk.TclError:
            pass

    def run_task(self, task):
        def worker():
            try:
                self.events.put(("task_done", (True, task())))
            except BaseException as exc:
                self.events.put(("task_done", (False, exc)))
        threading.Thread(target=worker, name="CGMD-BootstrapWorker", daemon=True).start()
        self.root.mainloop()
        if self._task_error is not None:
            raise self._task_error
        return self._task_result

    def close(self):
        try:
            self.root.destroy()
        except Exception:
            pass

def prepare_dependencies(system, ui: BootstrapUI) -> bool:
    from .config import load_config, save_config

    config = load_config()
    paths = _dependency_paths(system)
    missing = [name for name, info in paths.items() if not (info.path and info.executable_ok and not info.error)]
    needs_yt = "yt-dlp" in missing
    needs_ffmpeg_bundle = "ffmpeg" in missing or "ffprobe" in missing
    if not missing:
        return True

    for name, should_install in (("yt-dlp", needs_yt), ("ffmpeg", needs_ffmpeg_bundle)):
        # FFprobe is packaged with supported FFmpeg bundles, so a missing
        # ffprobe also triggers installation/reparation of the FFmpeg bundle.
        if not should_install:
            continue
        ui.update(f"Instalando {name}...", f"Arquitetura detectada: {system.architecture_label}", 0)
        try:
            def progress(stage: str, done: int, total: int):
                percent = (done / total * 100) if total else None
                ui.update(f"Instalando {name}...", f"{stage} • {done / 1048576:.1f} MiB" + (f" / {total / 1048576:.1f} MiB" if total else ""), percent)

            target, version = install_tool_from_release(name, system, progress=progress)
            if name == "yt-dlp":
                config["yt_dlp_path"] = ""
            else:
                config["ffmpeg_path"] = str(target)
                config["ffprobe_path"] = ""
            save_config(config)
            ui.update(f"{name} instalado", version or "Concluído", 100)
        except Exception as exc:
            ui.update(f"Não foi possível instalar {name} automaticamente", str(exc), 0)
            return False

    # Final verification after all automatic installations.
    time.sleep(0.25)
    final_paths = _dependency_paths(system)
    ok = all(info.path and info.executable_ok and not info.error for info in final_paths.values())
    if not ok:
        ui.update("Dependências ainda incompletas", "Abra Dependências para configurar manualmente.", 0)
    return ok


def run_installed() -> None:
    ensure_dirs()
    ensure_install_id()
    system = detect_system()

    # Run even --version probes and automatic dependency downloads on a worker
    # while Tk's event loop remains responsive. The earlier implementation used
    # update_idletasks() in the same thread, which could look frozen during HTTP I/O.
    ui = BootstrapUI()
    def initialize_dependencies():
        ui.update("Verificando yt-dlp, FFmpeg e FFprobe...", system.architecture_label, 5)
        ready = _dependency_ready(system)
        if not ready:
            ready = prepare_dependencies(system, ui)
        if ready:
            save_installation_baseline(load_config())
            ui.update("Tudo pronto", "Abrindo o aplicativo...", 100)
        else:
            ui.update("Dependências incompletas", "O aplicativo será aberto para permitir correção manual.", 100)
        return ready

    try:
        ready = ui.run_task(initialize_dependencies)
    except Exception as exc:
        ready = False
        # Log path is in the common per-user data directory; do not expose a console.
        try:
            from .logging_utils import setup_logging
            setup_logging(__import__("app.config", fromlist=["LOG_DIR"]).LOG_DIR).exception(
                "Falha durante a preparação inicial das dependências"
            )
        except Exception:
            pass
        show_startup_notice(
            "Não foi possível concluir a preparação automática das dependências.\n\n"
            f"Detalhes: {exc}\n\nO aplicativo será aberto para permitir configuração manual."
        )
    finally:
        ui.close()

    from .main import main as app_main
    app_main()


def _startup_recovery_choice(original_error: BaseException, *, repair_pending: bool) -> str:
    """Show explicit recovery choices instead of silently repeating a failed repair."""
    from .config import LOG_DIR
    import tkinter as tk
    from tkinter import ttk

    root = tk.Tk()
    root.withdraw()
    dialog = tk.Toplevel(root)
    dialog.title("ChatGPT Media Downloader — recuperação")
    dialog.geometry("690x360")
    dialog.resizable(False, False)
    dialog.transient(root)
    result = {"choice": "cancel"}

    frame = ttk.Frame(dialog, padding=20)
    frame.pack(fill="both", expand=True)
    heading = "A tentativa anterior de reparo não foi confirmada." if repair_pending else "O aplicativo encontrou uma falha grave ao iniciar."
    ttk.Label(frame, text=heading, font=("Segoe UI", 14, "bold"), wraplength=640).pack(anchor="w", pady=(0, 10))
    explanation = (
        "Escolha como continuar. Reparar baixa novamente o pacote da Release oficial e valida o SHA-256. "
        "Desinstalar remove os arquivos identificados do aplicativo e as configurações/ferramentas locais; "
        "as pastas de músicas e vídeos baixados não são removidas."
    )
    ttk.Label(frame, text=explanation, wraplength=640, justify="left").pack(anchor="w", pady=(0, 10))
    error_text = f"{type(original_error).__name__}: {str(original_error)}".strip()
    ttk.Label(
        frame,
        text=("Erro: " + (error_text[:600] if error_text else "detalhes não disponíveis") + "\n\nLogs: " + str(LOG_DIR)),
        wraplength=640, justify="left",
    ).pack(anchor="w", pady=(0, 18))

    actions = ttk.Frame(frame)
    actions.pack(fill="x", side="bottom")

    def choose(value: str) -> None:
        result["choice"] = value
        try:
            dialog.grab_release()
        except tk.TclError:
            pass
        dialog.destroy()

    ttk.Button(actions, text="Tentar reparar", command=lambda: choose("repair")).pack(side="left")
    ttk.Button(actions, text="Desinstalar aplicativo", command=lambda: choose("uninstall")).pack(side="left", padx=(8, 0))
    ttk.Button(actions, text="Cancelar", command=lambda: choose("cancel")).pack(side="right")
    dialog.protocol("WM_DELETE_WINDOW", lambda: choose("cancel"))
    dialog.bind("<Escape>", lambda _event: choose("cancel"))
    dialog.grab_set()
    dialog.focus_force()
    root.wait_window(dialog)
    root.destroy()
    return result["choice"]


def _startup_repair_target_root() -> Path:
    """Choose a repair target the current user can replace without admin rights."""
    from .config import IS_FROZEN
    if IS_FROZEN and os.name == "nt":
        install_id = ensure_install_id()
        return per_user_install_root(install_id, detect_system())
    return current_project_root()


def _offer_startup_repair(original_error: BaseException) -> bool:
    """Offer repair, uninstall, or cancel when the application cannot start."""
    from .config import (
        APP_DATA,
        IS_FROZEN,
        LOG_DIR,
        clear_startup_repair_pending,
        mark_startup_repair_pending,
        startup_repair_is_pending,
    )

    pending = startup_repair_is_pending()
    try:
        choice = _startup_recovery_choice(original_error, repair_pending=pending)
    except Exception as dialog_error:
        show_startup_notice(
            "Não foi possível abrir o painel de recuperação.\n\n"
            f"Erro original: {original_error}\nErro do painel: {dialog_error}\n\n"
            f"Consulte os logs em: {LOG_DIR}"
        )
        return False

    if choice == "uninstall":
        try:
            from .uninstall import launch_uninstaller

            install_root = current_project_root()
            if not _is_product_install(install_root):
                # Never delete an arbitrary folder such as Downloads or a source checkout.
                install_root = None
            launch_uninstaller(APP_DATA, install_root)
            show_startup_notice(
                "A desinstalação foi iniciada. O processo de limpeza continuará depois que esta janela fechar.\n\n"
                "As pastas escolhidas para salvar músicas e vídeos não serão removidas."
            )
            return True
        except Exception as uninstall_error:
            show_startup_notice(
                "Não foi possível iniciar a desinstalação.\n\n"
                f"Erro: {uninstall_error}\n\nSe a instalação estiver em Program Files, confirme a permissão do Windows."
            )
            return False

    if choice != "repair":
        return False

    # A retry must be explicit: clear a previous failed hand-off marker only
    # after the user chooses to try again. No repair is launched automatically.
    if pending and not clear_startup_repair_pending():
        show_startup_notice(
            "Não foi possível limpar o marcador da tentativa anterior.\n\n"
            f"Verifique as permissões e consulte: {LOG_DIR}"
        )
        return False

    pending_written = False
    scheduled = False
    try:
        from .app_update import check_repair_candidate, prepare_update, schedule_apply_update

        candidate = check_repair_candidate(VERSION, frozen=IS_FROZEN)
        prepared = prepare_update(candidate, target_root=_startup_repair_target_root())
        mark_startup_repair_pending(candidate.version)
        pending_written = True
        try:
            schedule_apply_update(prepared, launch_after=True, startup_repair=True)
            scheduled = True
        except Exception:
            clear_startup_repair_pending()
            pending_written = False
            raise

        show_startup_notice(
            "O pacote oficial foi baixado e validado. O aplicativo será fechado para aplicar o reparo.\n\n"
            "A nova interface precisa abrir para confirmar a recuperação; se isso falhar, você poderá escolher "
            "reparar novamente ou desinstalar na próxima abertura."
        )
        return True
    except Exception as repair_error:
        if pending_written and not scheduled:
            clear_startup_repair_pending()
        try:
            from .locking import show_startup_notice as notify
            notify(
                "O reparo automático não pôde ser preparado.\n\n"
                f"Erro de inicialização: {original_error}\n\nFalha no reparo: {repair_error}\n\n"
                "Confira sua conexão e a existência de uma Release oficial no GitHub."
            )
        except Exception:
            pass
        return False


def main() -> None:
    guard = None
    try:
        ensure_dirs()
        handoff_token = next((arg.split("=", 1)[1] for arg in sys.argv[1:] if arg.startswith("--handoff-token=")), None)
        guard = InstanceGuard()
        if not guard.acquire(handoff_token=handoff_token):
            show_startup_notice(guard.reason)
            return
        try:
            install_id = ensure_install_id()
            system = detect_system()
            frozen = bool(getattr(sys, "frozen", False))
            source = current_project_root()

            if "--installed" in sys.argv[1:]:
                installed_root = Path(sys.executable).resolve().parent if frozen else source
                if frozen and os.name == "nt":
                    try:
                        if sync_portable_entrypoint(installed_root, install_id, Path(sys.executable).resolve()):
                            from .logging_utils import setup_logging
                            from .config import LOG_DIR
                            setup_logging(LOG_DIR).info("Entrada portátil sincronizada com a versão instalada %s.", VERSION)
                    except Exception:
                        pass
                if os.name == "nt":
                    create_desktop_shortcut(installed_root)
                elif system.os_name == "Linux":
                    create_linux_desktop_entry(installed_root)
                run_installed()
                return

            if frozen:
                install_root, migrated = ensure_frozen_installation(Path(sys.executable).resolve(), install_id, system)
            else:
                install_root, migrated = ensure_installation(source, install_id, system)

            if os.name == "nt":
                create_desktop_shortcut(install_root)
            elif system.os_name == "Linux":
                create_linux_desktop_entry(install_root)
            if migrated:
                token = guard.create_handoff(install_root)
                try:
                    child = relaunch_from_install(install_root, token)
                    guard.set_handoff_child(token, child.pid)
                except Exception:
                    guard.clear_handoff(token)
                    raise
                if os.name == "nt" and not frozen:
                    installed_version = _installed_version(install_root, install_id)
                    if not _version_is_newer(installed_version, VERSION):
                        schedule_source_cleanup(source, install_root)
                    else:
                        # This was a downgrade-prevention handoff; keep the old source copy intact.
                        try:
                            from .logging_utils import setup_logging
                            from .config import LOG_DIR
                            setup_logging(LOG_DIR).info(
                                "Reabertura encaminhada para instalação mais nova %s; origem antiga preservada.",
                                installed_version,
                            )
                        except Exception:
                            pass
                return
            run_installed()
        finally:
            guard.release()
    except Exception as exc:
        # pythonw/launcher.vbs has no console, so failures must be visible and logged.
        try:
            from .config import LOG_DIR
            from .logging_utils import setup_logging
            logger = setup_logging(LOG_DIR)
            logger.exception("Falha de inicialização/atualização do aplicativo")
        except Exception:
            pass
        repaired = _offer_startup_repair(exc)
        if not repaired:
            show_startup_notice(
                "O ChatGPT Media Downloader não conseguiu concluir a inicialização ou atualização.\n\n"
                f"Detalhes: {exc}\n\n"
                "A versão anterior foi preservada quando a falha ocorreu durante a troca de arquivos. "
                "Consulte os logs na pasta de dados do aplicativo."
            )
    finally:
        if guard is not None:
            guard.release()


if __name__ == "__main__":
    main()

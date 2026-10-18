from __future__ import annotations

import os
import platform as _platform
import struct
import subprocess
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class SystemInfo:
    os_name: str
    os_label: str
    architecture: str
    architecture_label: str
    machine: str
    python_bits: int


def _windows_machine() -> str:
    return (
        os.environ.get("PROCESSOR_ARCHITEW6432")
        or os.environ.get("PROCESSOR_ARCHITECTURE")
        or _platform.machine()
    ).upper()


def _normalise_windows(machine: str) -> str:
    if machine in {"AMD64", "X86_64"}:
        return "x64"
    if machine in {"X86", "I386", "I486", "I586", "I686"}:
        return "x86"
    if machine in {"ARM64", "AARCH64"}:
        return "ARM64"
    return machine.lower() or "unknown"


def _normalise_unix(machine: str) -> str:
    m = machine.lower()
    if m in {"x86_64", "amd64"}:
        return "x64"
    if m in {"i386", "i486", "i586", "i686", "x86"}:
        return "x86"
    if m in {"aarch64", "arm64"}:
        return "ARM64"
    if m.startswith("armv7") or m in {"arm", "armhf"}:
        return "ARMv7"
    return machine.lower() or "unknown"


def detect_system() -> SystemInfo:
    os_name = _platform.system()
    machine = _windows_machine() if os_name == "Windows" else _platform.machine()
    bits = struct.calcsize("P") * 8

    if os_name == "Windows":
        arch = _normalise_windows(machine)
        label = f"Windows {arch}"
    elif os_name == "Linux":
        arch = _normalise_unix(machine)
        label = f"Linux {arch}"
    elif os_name == "Darwin":
        raw = machine.lower()
        if raw in {"arm64", "aarch64"}:
            arch = "Apple Silicon"
        elif raw in {"x86_64", "amd64"}:
            arch = "Intel"
        else:
            arch = raw or "unknown"
        label = f"macOS {arch}"
    else:
        arch = _normalise_unix(machine)
        label = f"{os_name} {arch}"

    return SystemInfo(
        os_name=os_name,
        os_label=label,
        architecture=arch,
        architecture_label=label,
        machine=machine,
        python_bits=bits,
    )


def is_supported(system: SystemInfo) -> bool:
    supported = {
        ("Windows", "x86"), ("Windows", "x64"), ("Windows", "ARM64"),
        ("Linux", "x86"), ("Linux", "x64"), ("Linux", "ARM64"), ("Linux", "ARMv7"),
        ("Darwin", "Intel"), ("Darwin", "Apple Silicon"),
    }
    return (system.os_name, system.architecture) in supported


def detect_system_theme() -> Literal["light", "dark"]:
    """Best-effort native theme detection with no third-party dependency."""
    try:
        if os.name == "nt":
            import winreg
            key_path = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
                value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
                return "light" if int(value) else "dark"
    except (OSError, ValueError, ImportError):
        pass

    system = _platform.system()
    if system == "Darwin":
        try:
            completed = subprocess.run(
                ["defaults", "read", "-g", "AppleInterfaceStyle"],
                capture_output=True, text=True, timeout=2, check=False,
            )
            return "dark" if "Dark" in (completed.stdout or "") else "light"
        except (OSError, subprocess.TimeoutExpired):
            pass

    if system == "Linux":
        env_hints = " ".join(
            os.environ.get(name, "") for name in ("GTK_THEME", "COLOR_SCHEME", "QT_STYLE_OVERRIDE")
        ).lower()
        if "dark" in env_hints:
            return "dark"
        try:
            completed = subprocess.run(
                ["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"],
                capture_output=True, text=True, timeout=2, check=False,
            )
            out = (completed.stdout or "").lower()
            if "prefer-dark" in out:
                return "dark"
            if "prefer-light" in out:
                return "light"
        except (OSError, subprocess.TimeoutExpired):
            pass

    return "light"

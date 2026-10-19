from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
import zipfile
import tarfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .config import TOOLS_DIR
from .platform import SystemInfo
from .process_utils import hidden_subprocess_kwargs
from .security import safe_archive_member_path

MAX_ARCHIVE_MEMBERS = 100_000
MAX_ARCHIVE_UNPACKED_BYTES = 2 * 1024 * 1024 * 1024


@dataclass
class ToolInfo:
    name: str
    path: Optional[Path]
    version: str = ""
    architecture: str = "unknown"
    source: str = ""
    executable_ok: bool = False
    error: str = ""


def _candidate_names(name: str, system: SystemInfo) -> list[str]:
    if name == "yt-dlp":
        if system.os_name == "Windows":
            if system.architecture == "x86":
                return ["yt-dlp_x86.exe"]
            if system.architecture == "ARM64":
                return ["yt-dlp_arm64.exe"]
            return ["yt-dlp.exe"]
        if system.os_name == "Linux":
            if system.architecture == "ARM64":
                return ["yt-dlp_linux_aarch64"]
            if system.architecture == "ARMv7":
                return ["yt-dlp_linux_armv7l", "yt-dlp_linux_armv7l.zip"]
            if system.architecture == "x64":
                return ["yt-dlp_linux"]
            if system.architecture == "x86":
                return ["yt-dlp"]
            return ["yt-dlp"]
        if system.os_name == "Darwin":
            return ["yt-dlp_macos"]
    if name == "ffmpeg":
        return [f"ChatGPT.MediaDownloader.ffmpeg{'.exe' if system.os_name == 'Windows' else ''}", "ffmpeg.exe" if system.os_name == "Windows" else "ffmpeg"]
    if name == "ffprobe":
        return [f"ChatGPT.MediaDownloader.ffprobe{'.exe' if system.os_name == 'Windows' else ''}", "ffprobe.exe" if system.os_name == "Windows" else "ffprobe"]
    return [name]


def _iter_manual_paths(configured: str) -> list[Path]:
    if not configured:
        return []
    return [Path(configured).expanduser()]


def _path_in_app_dir(name: str, system: SystemInfo) -> list[Path]:
    candidates = []
    for filename in _candidate_names(name, system):
        candidates.append(TOOLS_DIR / filename)
    return candidates


def _path_from_system(name: str, system: SystemInfo) -> list[Path]:
    names = _candidate_names(name, system)
    candidates: list[Path] = []
    for n in names:
        which = shutil.which(n)
        if which:
            candidates.append(Path(which))
    if name == "yt-dlp":
        for n in ("yt-dlp.exe", "yt-dlp"):
            which = shutil.which(n)
            if which:
                candidates.append(Path(which))
    return candidates


def locate_tool(name: str, configured: str, system: SystemInfo) -> tuple[Optional[Path], str]:
    # Required order: manual -> private app -> system PATH.
    for path in _iter_manual_paths(configured):
        if path.is_file():
            return path, "configuração manual"
    for path in _path_in_app_dir(name, system):
        if path.is_file():
            return path, "pasta privada da aplicação"
    for path in _path_from_system(name, system):
        if path.is_file():
            return path, "PATH do sistema"
    return None, ""


def _run_version(path: Path, args: list[str]) -> str:
    try:
        completed = subprocess.run(
            [str(path), *args],
            capture_output=True,
            text=True,
            timeout=12,
            check=False,
            **hidden_subprocess_kwargs(),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"erro: {exc}"
    output = (completed.stdout or completed.stderr or "").strip()
    return output.splitlines()[0] if output else f"código {completed.returncode}"


def _elf_arch(path: Path) -> str:
    try:
        data = path.read_bytes()[:64]
        if len(data) < 20 or data[:4] != b"\x7fELF":
            return "unknown"
        ei_class = data[4]
        endian = "<" if data[5] == 1 else ">"
        e_machine = int.from_bytes(data[18:20], "little" if endian == "<" else "big")
        if e_machine == 62:
            return "x64"
        if e_machine in {183, 184}:
            return "ARM64"
        if e_machine == 40:
            return "ARMv7"
        if e_machine == 3:
            return "x86"
        return f"ELF:{e_machine}"
    except OSError:
        return "unknown"


def _pe_arch(path: Path) -> str:
    try:
        data = path.read_bytes()
        if len(data) < 0x40 or data[:2] != b"MZ":
            return "unknown"
        pe_offset = int.from_bytes(data[0x3C:0x40], "little")
        if pe_offset + 6 > len(data) or data[pe_offset:pe_offset + 4] != b"PE\x00\x00":
            return "unknown"
        machine = int.from_bytes(data[pe_offset + 4:pe_offset + 6], "little")
        return {0x8664: "x64", 0x014C: "x86", 0xAA64: "ARM64"}.get(machine, f"PE:{machine:04X}")
    except OSError:
        return "unknown"


def detect_binary_arch(path: Path, system: SystemInfo) -> str:
    if system.os_name == "Windows" or path.suffix.lower() == ".exe":
        return _pe_arch(path)
    try:
        magic = path.read_bytes()[:4]
    except OSError:
        return "unknown"
    if magic == b"\x7fELF":
        return _elf_arch(path)
    # macOS fat/Mach-O detection is intentionally conservative.
    if system.os_name == "Darwin":
        try:
            value = int.from_bytes(path.read_bytes()[:4], "big")
            if value in {0xCAFEBABE, 0xBEBAFECA}:
                return "universal"
            if value in {0xFEEDFACF, 0xCFFAEDFE}:
                return "ARM64" if system.architecture == "Apple Silicon" else "Intel"
        except OSError:
            pass
    return "unknown"


def inspect_tool(name: str, configured: str, system: SystemInfo) -> ToolInfo:
    path, source = locate_tool(name, configured, system)
    info = ToolInfo(name=name, path=path, source=source)
    if not path:
        return info

    if name == "yt-dlp":
        info.version = _run_version(path, ["--version"])
    elif name == "ffmpeg":
        info.version = _run_version(path, ["-version"])
    else:
        info.version = _run_version(path, ["-version"])
    info.architecture = detect_binary_arch(path, system)
    info.executable_ok = not info.version.startswith("erro:")
    if info.architecture not in {"unknown", "universal"} and system.architecture in {"x64", "x86", "ARM64", "ARMv7"}:
        expected = system.architecture
        if info.name == "yt-dlp" and system.os_name == "Darwin":
            expected = "universal"
        if info.architecture not in {expected, "universal"}:
            info.error = f"Arquitetura incompatível: binário={info.architecture}, sistema={expected}."
    return info


def extract_archive(archive: Path, destination: Path) -> None:
    """Extract only regular files/directories after validating every archive member."""
    destination.mkdir(parents=True, exist_ok=True)
    temp_dir = destination / ".extracting"
    if temp_dir.exists():
        shutil.rmtree(temp_dir, ignore_errors=True)
    temp_dir.mkdir(parents=True, exist_ok=True)
    try:
        if archive.suffix.lower() == ".zip":
            with zipfile.ZipFile(archive) as zf:
                members = zf.infolist()
                if len(members) > MAX_ARCHIVE_MEMBERS or sum(max(0, item.file_size) for item in members) > MAX_ARCHIVE_UNPACKED_BYTES:
                    raise ValueError("Arquivo compactado excede o limite de conteúdo permitido.")
                for member in members:
                    safe_archive_member_path(temp_dir, member.filename)
                    if member.flag_bits & 0x1:
                        raise ValueError("Arquivo compactado criptografado não é aceito.")
                    mode = (member.external_attr >> 16) & 0xFFFF
                    file_type = stat.S_IFMT(mode)
                    if file_type == stat.S_IFLNK or (file_type and file_type not in {stat.S_IFREG, stat.S_IFDIR}):
                        raise ValueError("Arquivo compactado contém link ou arquivo especial inseguro.")
                zf.extractall(temp_dir)
        elif archive.name.endswith(".tar.xz"):
            with tarfile.open(archive, "r:xz") as tf:
                members = tf.getmembers()
                total_unpacked = sum(member.size for member in members if member.isreg())
                if len(members) > MAX_ARCHIVE_MEMBERS or total_unpacked > MAX_ARCHIVE_UNPACKED_BYTES:
                    raise ValueError("Arquivo compactado excede o limite de conteúdo permitido.")
                for member in members:
                    safe_archive_member_path(temp_dir, member.name)
                    if not (member.isdir() or member.isreg()):
                        raise ValueError("Arquivo compactado contém link ou arquivo especial inseguro.")
                tf.extractall(temp_dir)
        else:
            raise ValueError(f"Formato de arquivo não suportado: {archive.name}")
        allowed_tools = {
            "ffmpeg", "ffmpeg.exe", "ffprobe", "ffprobe.exe", "yt-dlp", "yt-dlp.exe",
            "yt-dlp_x86.exe", "yt-dlp_arm64.exe", "yt-dlp_linux", "yt-dlp_linux_aarch64",
        }
        for candidate in temp_dir.rglob("*"):
            if not candidate.is_file() or candidate.name.lower() not in allowed_tools:
                continue
            target = destination / candidate.name
            # Never follow a pre-existing symlink or replace a directory unexpectedly.
            if target.is_symlink() or (target.exists() and not target.is_file()):
                raise ValueError("O destino da ferramenta contém um caminho inseguro.")
            staged = destination / f".{candidate.name}.staged"
            if staged.is_symlink() or (staged.exists() and not staged.is_file()):
                raise ValueError("O arquivo temporário da ferramenta contém um caminho inseguro.")
            try:
                shutil.copyfile(candidate, staged)
                if os.name != "nt":
                    staged.chmod(staged.stat().st_mode | 0o111)
                os.replace(staged, target)
            finally:
                staged.unlink(missing_ok=True)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

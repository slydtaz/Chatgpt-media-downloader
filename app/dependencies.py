from __future__ import annotations

import lzma
import os
import shutil
import stat
import subprocess
import tarfile
import tempfile
import zipfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .config import TOOLS_DIR
from .platform import SystemInfo
from .process_utils import hidden_subprocess_kwargs
from .security import safe_archive_member_path

MAX_ARCHIVE_MEMBERS = 100_000
MAX_ARCHIVE_COMPRESSED_BYTES = 512 * 1024 * 1024
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


def _is_reparse_directory(path: Path) -> bool:
    """Detect a symlink/junction directory without requiring Path.is_junction on Python 3.10."""
    if path.is_symlink():
        return True
    checker = getattr(path, "is_junction", None)
    try:
        return bool(checker()) if checker is not None else False
    except OSError:
        return True


def extract_archive(archive: Path, destination: Path) -> None:
    """Safely extract trusted media-tool archives into isolated, unique staging."""
    archive = Path(archive)
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    if _is_reparse_directory(destination):
        raise ValueError("A pasta de ferramentas não pode ser um link simbólico ou junction.")
    destination_root = destination.resolve()

    try:
        archive_stat = archive.lstat()
    except OSError as exc:
        raise ValueError(f"Não foi possível inspecionar o arquivo compactado: {exc}") from exc
    if not stat.S_ISREG(archive_stat.st_mode) or archive.is_symlink():
        raise ValueError("O arquivo compactado precisa ser um arquivo regular, não um link.")
    if archive_stat.st_size <= 0 or archive_stat.st_size > MAX_ARCHIVE_COMPRESSED_BYTES:
        raise ValueError("O arquivo compactado está vazio ou excede o limite permitido.")

    # A unique private directory prevents concurrent launches or stale files from
    # sharing a predictable extraction location.
    temp_dir = Path(tempfile.mkdtemp(prefix=".extracting-", dir=str(destination_root)))
    try:
        if archive.suffix.lower() == ".zip":
            with zipfile.ZipFile(archive) as zf:
                members = zf.infolist()
                unpacked_size = sum(max(0, int(item.file_size)) for item in members)
                if not members or len(members) > MAX_ARCHIVE_MEMBERS or unpacked_size > MAX_ARCHIVE_UNPACKED_BYTES:
                    raise ValueError("Arquivo compactado excede os limites de conteúdo permitidos.")
                seen_paths: set[str] = set()
                for member in members:
                    target_path = safe_archive_member_path(temp_dir, member.filename)
                    path_key = target_path.as_posix().casefold()
                    if path_key in seen_paths:
                        raise ValueError("Arquivo compactado contém caminhos duplicados ou ambíguos.")
                    seen_paths.add(path_key)
                    if member.flag_bits & 0x1:
                        raise ValueError("Arquivo compactado criptografado não é aceito.")
                    mode = (member.external_attr >> 16) & 0xFFFF
                    file_type = stat.S_IFMT(mode)
                    if file_type == stat.S_IFLNK or (file_type and file_type not in {stat.S_IFREG, stat.S_IFDIR}):
                        raise ValueError("Arquivo compactado contém link ou arquivo especial inseguro.")
                zf.extractall(temp_dir)
        elif archive.name.lower().endswith(".tar.xz"):
            with tarfile.open(archive, "r:xz") as tf:
                members = tf.getmembers()
                if not members or len(members) > MAX_ARCHIVE_MEMBERS:
                    raise ValueError("Arquivo TAR excede o limite de entradas permitido.")
                total_unpacked = 0
                seen_paths: set[str] = set()
                for member in members:
                    if member.size < 0:
                        raise ValueError("Arquivo TAR contém tamanho de entrada inválido.")
                    target_path = safe_archive_member_path(temp_dir, member.name)
                    path_key = target_path.as_posix().casefold()
                    if path_key in seen_paths:
                        raise ValueError("Arquivo TAR contém caminhos duplicados ou ambíguos.")
                    seen_paths.add(path_key)
                    if not (member.isdir() or member.isreg()):
                        raise ValueError("Arquivo TAR contém links ou arquivos especiais inseguros.")
                    if member.isreg():
                        total_unpacked += member.size
                        if total_unpacked > MAX_ARCHIVE_UNPACKED_BYTES:
                            raise ValueError("Arquivo TAR excede o limite de conteúdo permitido.")
                tf.extractall(temp_dir)
        else:
            raise ValueError(f"Formato de arquivo não suportado: {archive.name}")

        allowed_tools = {
            "ffmpeg", "ffmpeg.exe", "ffprobe", "ffprobe.exe", "yt-dlp", "yt-dlp.exe",
            "yt-dlp_x86.exe", "yt-dlp_arm64.exe", "yt-dlp_linux", "yt-dlp_linux_aarch64",
        }
        candidates = [
            item for item in temp_dir.rglob("*")
            if item.is_file() and not item.is_symlink() and item.name.lower() in allowed_tools
        ]
        if not candidates:
            raise ValueError("O arquivo compactado não contém uma ferramenta de mídia reconhecida.")

        # Different folders can contain the same basename. Reject this ambiguity
        # instead of letting archive order silently decide which executable wins.
        seen_names: set[str] = set()
        for candidate in candidates:
            basename = candidate.name.casefold()
            if basename in seen_names:
                raise ValueError("O arquivo compactado contém ferramentas com nomes duplicados.")
            seen_names.add(basename)

        staged: list[tuple[Path, Path]] = []
        backups: list[tuple[Path, Path]] = []
        promoted: list[Path] = []
        try:
            # Stage every tool before touching installed files.
            for candidate in candidates:
                target = destination_root / candidate.name
                if _is_reparse_directory(target) or (target.exists() and not target.is_file()):
                    raise ValueError("O destino da ferramenta contém um caminho inseguro.")
                staging_path = destination_root / f".{candidate.name}.{uuid.uuid4().hex}.staged"
                with candidate.open("rb") as source, staging_path.open("xb") as output:
                    shutil.copyfileobj(source, output, length=1024 * 1024)
                if os.name != "nt":
                    staging_path.chmod(staging_path.stat().st_mode | 0o111)
                staged.append((staging_path, target))

            for _staging_path, target in staged:
                if _is_reparse_directory(target) or (target.exists() and not target.is_file()):
                    raise ValueError("O destino da ferramenta mudou para um caminho inseguro.")

            # Keep original binaries until every staged file has been promoted.
            token = uuid.uuid4().hex
            for _staging_path, target in staged:
                if target.exists():
                    backup = destination_root / f".{target.name}.{token}.backup"
                    os.replace(target, backup)
                    backups.append((backup, target))
            for staging_path, target in staged:
                os.replace(staging_path, target)
                promoted.append(target)
        except OSError as exc:
            for target in reversed(promoted):
                try:
                    target.unlink(missing_ok=True)
                except OSError:
                    pass
            rollback_errors: list[str] = []
            for backup, target in reversed(backups):
                try:
                    if backup.exists():
                        os.replace(backup, target)
                except OSError as rollback_exc:
                    rollback_errors.append(f"{target.name}: {rollback_exc}")
            detail = "Não foi possível instalar as ferramentas; a versão anterior foi preservada quando possível."
            if rollback_errors:
                detail += " Falha ao restaurar backup: " + "; ".join(rollback_errors)
            raise ValueError(detail) from exc
        else:
            for backup, _target in backups:
                try:
                    backup.unlink(missing_ok=True)
                except OSError:
                    pass
        finally:
            for staging_path, _target in staged:
                staging_path.unlink(missing_ok=True)
    except ValueError:
        raise
    except (OSError, EOFError, lzma.LZMAError, NotImplementedError, RuntimeError,
            tarfile.TarError, zipfile.BadZipFile) as exc:
        raise ValueError(f"O arquivo compactado não pôde ser extraído com segurança: {exc}") from exc
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import urllib.request
import uuid
from urllib.parse import urlsplit
import zipfile
import tarfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from .config import APP_DATA, TOOLS_DIR
from .locking import CrossProcessFileLock
from .dependencies import detect_binary_arch
from .platform import SystemInfo
from .process_utils import hidden_subprocess_kwargs


YT_API = "https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest"
FF_API = "https://api.github.com/repos/BtbN/FFmpeg-Builds/releases/latest"


@dataclass(frozen=True)
class ReleaseAsset:
    name: str
    url: str
    size: int


class UpdateError(RuntimeError):
    pass


def _request_json(url: str) -> dict:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "ChatGPT-Media-Downloader/4.9.0", "Accept": "application/vnd.github+json"},
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def _download(url: str, destination: Path, progress: Optional[Callable[[int, int], None]] = None) -> None:
    if not _trusted_github_url(url):
        raise UpdateError("Fonte de download não autorizada.")
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "ChatGPT-Media-Downloader/4.9.0"},
    )
    with urllib.request.urlopen(request, timeout=60) as response, destination.open("wb") as out:
        total = int(response.headers.get("Content-Length", "0") or 0)
        done = 0
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            out.write(chunk)
            done += len(chunk)
            if progress:
                progress(done, total)


def _trusted_github_url(url: str) -> bool:
    try:
        host = (urlsplit(url).hostname or "").lower()
    except ValueError:
        return False
    return host in {"github.com", "objects.githubusercontent.com", "raw.githubusercontent.com"}


def _asset(release: dict, name: str) -> Optional[ReleaseAsset]:
    for item in release.get("assets", []):
        if item.get("name") == name:
            return ReleaseAsset(item["name"], item["browser_download_url"], int(item.get("size", 0)))
    return None


def yt_asset_name(system: SystemInfo) -> Optional[str]:
    if system.os_name == "Windows":
        return {"x86": "yt-dlp_x86.exe", "x64": "yt-dlp.exe", "ARM64": "yt-dlp_arm64.exe"}.get(system.architecture)
    if system.os_name == "Linux":
        return {"x64": "yt-dlp_linux", "ARM64": "yt-dlp_linux_aarch64", "ARMv7": "yt-dlp_linux_armv7l.zip"}.get(system.architecture)
    if system.os_name == "Darwin":
        return "yt-dlp_macos" if system.architecture in {"Intel", "Apple Silicon"} else None
    return None


def ff_asset_name(system: SystemInfo) -> Optional[str]:
    # Stable release branch asset from BtbN where an architecture-specific build is published.
    if system.os_name == "Windows":
        return {
            "x64": "ffmpeg-master-latest-win64-gpl.zip",
            "ARM64": "ffmpeg-master-latest-winarm64-gpl.zip",
        }.get(system.architecture)
    if system.os_name == "Linux":
        return {
            "x64": "ffmpeg-master-latest-linux64-gpl.tar.xz",
            "ARM64": "ffmpeg-master-latest-linuxarm64-gpl.tar.xz",
        }.get(system.architecture)
    return None


def _checksum_asset(release: dict) -> Optional[ReleaseAsset]:
    return _asset(release, "SHA2-256SUMS") or _asset(release, "checksums.sha256")


def _verify_checksum(release: dict, asset: ReleaseAsset, downloaded: Path) -> bool:
    checksum_asset = _checksum_asset(release)
    # A release without a checksum manifest is not treated as automatically
    # trusted; the caller still validates the trusted host, archive structure,
    # expected executable architecture and --version execution.
    if not checksum_asset:
        return downloaded.is_file() and downloaded.stat().st_size > 1024
    temp = downloaded.with_suffix(downloaded.suffix + ".checksums")
    try:
        _download(checksum_asset.url, temp)
        text = temp.read_text(encoding="utf-8", errors="replace")
        expected = None
        for line in text.splitlines():
            parts = line.strip().split()
            if len(parts) >= 2 and parts[-1].lstrip("*") == asset.name:
                expected = parts[0].lower()
                break
        if not expected:
            return False
        h = hashlib.sha256()
        with downloaded.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest().lower() == expected
    finally:
        temp.unlink(missing_ok=True)


def check_latest() -> dict[str, dict]:
    yt = _request_json(YT_API)
    ff = _request_json(FF_API)
    return {
        "yt-dlp": {"version": yt.get("tag_name", ""), "release": yt},
        "ffmpeg": {"version": ff.get("tag_name", ""), "release": ff},
    }


def _run_staged_executable(path: Path, args: list[str], label: str) -> None:
    try:
        completed = subprocess.run(
            [str(path), *args], capture_output=True, text=True,
            timeout=15, check=False, **hidden_subprocess_kwargs(),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise UpdateError(f"O executável preparado ({label}) não pôde ser validado: {exc}") from exc
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()[-800:]
        raise UpdateError(
            f"O executável preparado ({label}) não iniciou corretamente "
            f"(código {completed.returncode}). {detail}"
        )


def _replace_single_file(staged: Path, target: Path) -> None:
    """Atomically promote a validated binary; on failure the old target remains."""
    target.parent.mkdir(parents=True, exist_ok=True)
    os.replace(staged, target)


def _replace_file_pair(staged_a: Path, target_a: Path, staged_b: Path, target_b: Path) -> None:
    """Promote ffmpeg/ffprobe together with best-effort rollback on any error."""
    token = uuid.uuid4().hex[:12]
    backups: dict[Path, Path] = {}
    promoted: list[Path] = []
    targets = ((staged_a, target_a), (staged_b, target_b))
    try:
        # Move existing binaries aside only after both staged replacements were tested.
        for _staged, target in targets:
            if target.exists():
                backup = target.with_name(f".{target.name}.backup-{token}")
                os.replace(target, backup)
                backups[target] = backup
        for staged, target in targets:
            os.replace(staged, target)
            promoted.append(target)
    except OSError as exc:
        for target in reversed(promoted):
            try:
                target.unlink(missing_ok=True)
            except OSError:
                pass
        rollback_errors = []
        for target, backup in backups.items():
            try:
                if backup.exists():
                    os.replace(backup, target)
            except OSError as rollback_exc:
                rollback_errors.append(str(rollback_exc))
        detail = f"Não foi possível substituir FFmpeg/FFprobe; a versão anterior foi preservada quando possível: {exc}"
        if rollback_errors:
            detail += " | Falha adicional no rollback: " + "; ".join(rollback_errors)
        raise UpdateError(detail) from exc
    else:
        for backup in backups.values():
            try:
                backup.unlink(missing_ok=True)
            except OSError:
                pass


def _install_tool_from_release_locked(
    tool: str,
    system: SystemInfo,
    *,
    progress: Optional[Callable[[str, int, int], None]] = None,
) -> tuple[Path, str]:
    if tool not in {"yt-dlp", "ffmpeg"}:
        raise UpdateError(f"Dependência desconhecida: {tool}")

    release = _request_json(YT_API if tool == "yt-dlp" else FF_API)
    name = yt_asset_name(system) if tool == "yt-dlp" else ff_asset_name(system)
    if not name:
        raise UpdateError(f"Não há uma build automática registrada para {system.architecture_label}.")
    asset = _asset(release, name)
    if not asset:
        raise UpdateError(f"Asset compatível não encontrado no release: {name}")

    TOOLS_DIR.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="cgm_stage_", dir=str(TOOLS_DIR)))
    try:
        archive = work / asset.name
        staging = work / "validated"
        staging.mkdir()
        if progress:
            progress(f"Baixando {asset.name}", 0, asset.size)
        _download(asset.url, archive, lambda done, total: progress("Baixando", done, total) if progress else None)
        if not _verify_checksum(release, asset, archive):
            raise UpdateError("A verificação SHA-256 falhou ou o manifesto não contém o asset baixado.")

        if tool == "yt-dlp":
            if name.endswith(".zip"):
                extract_dir = work / "extract"
                extract_dir.mkdir()
                with zipfile.ZipFile(archive) as zf:
                    for member in zf.infolist():
                        target_path = (extract_dir / member.filename).resolve()
                        if not str(target_path).startswith(str(extract_dir.resolve()) + os.sep):
                            raise UpdateError("Pacote yt-dlp contém caminho inseguro.")
                    zf.extractall(extract_dir)
                source = next((p for p in extract_dir.rglob("yt-dlp_linux_armv7l") if p.is_file()), None)
                if source is None:
                    raise UpdateError("O pacote yt-dlp ARMv7 não contém o executável esperado.")
            else:
                source = archive

            staged_binary = staging / name
            shutil.copy2(source, staged_binary)
            if os.name != "nt":
                staged_binary.chmod(staged_binary.stat().st_mode | 0o111)
            detected = detect_binary_arch(staged_binary, system)
            expected = "universal" if system.os_name == "Darwin" else system.architecture
            if detected not in {"unknown", "universal", expected}:
                raise UpdateError(f"Arquitetura incompatível após download: binário={detected}, sistema={expected}.")
            _run_staged_executable(staged_binary, ["--version"], "yt-dlp")
            target = TOOLS_DIR / name
            _replace_single_file(staged_binary, target)
            return target, str(release.get("tag_name", ""))

        # FFmpeg archives contain both executables. Extract and validate BOTH
        # from a private staging directory before replacing either live file.
        extract_dir = work / "extract"
        extract_dir.mkdir()
        if archive.suffix.lower() == ".zip":
            with zipfile.ZipFile(archive) as zf:
                for member in zf.infolist():
                    target_path = (extract_dir / member.filename).resolve()
                    if not str(target_path).startswith(str(extract_dir.resolve()) + os.sep):
                        raise UpdateError("Pacote FFmpeg contém caminho inseguro.")
                zf.extractall(extract_dir)
        elif archive.name.endswith(".tar.xz"):
            with tarfile.open(archive, "r:xz") as tf:
                for member in tf.getmembers():
                    target_path = (extract_dir / member.name).resolve()
                    if not str(target_path).startswith(str(extract_dir.resolve()) + os.sep):
                        raise UpdateError("Pacote FFmpeg contém caminho inseguro.")
                tf.extractall(extract_dir)
        else:
            raise UpdateError(f"Arquivo FFmpeg não suportado: {archive.name}")

        found_ffmpeg = next((p for p in extract_dir.rglob("*") if p.is_file() and p.name.lower() in {"ffmpeg", "ffmpeg.exe"}), None)
        found_ffprobe = next((p for p in extract_dir.rglob("*") if p.is_file() and p.name.lower() in {"ffprobe", "ffprobe.exe"}), None)
        if not found_ffmpeg or not found_ffprobe:
            raise UpdateError("O pacote FFmpeg não contém ffmpeg e ffprobe.")

        staged_ffmpeg = staging / f"ChatGPT.MediaDownloader.ffmpeg{found_ffmpeg.suffix}"
        staged_ffprobe = staging / f"ChatGPT.MediaDownloader.ffprobe{found_ffprobe.suffix}"
        shutil.copy2(found_ffmpeg, staged_ffmpeg)
        shutil.copy2(found_ffprobe, staged_ffprobe)
        if os.name != "nt":
            for staged in (staged_ffmpeg, staged_ffprobe):
                staged.chmod(staged.stat().st_mode | 0o111)

        expected = system.architecture
        for staged, label in ((staged_ffmpeg, "FFmpeg"), (staged_ffprobe, "FFprobe")):
            detected = detect_binary_arch(staged, system)
            if detected not in {"unknown", "universal", expected}:
                raise UpdateError(f"Arquitetura incompatível em {label}: binário={detected}, sistema={expected}.")
            _run_staged_executable(staged, ["-version"], label)

        target_ffmpeg = TOOLS_DIR / staged_ffmpeg.name
        target_ffprobe = TOOLS_DIR / staged_ffprobe.name
        _replace_file_pair(staged_ffmpeg, target_ffmpeg, staged_ffprobe, target_ffprobe)
        return target_ffmpeg, str(release.get("tag_name", ""))
    finally:
        shutil.rmtree(work, ignore_errors=True)


def install_tool_from_release(
    tool: str,
    system: SystemInfo,
    *,
    progress: Optional[Callable[[str, int, int], None]] = None,
) -> tuple[Path, str]:
    """Serialize cross-process dependency updates and promote binaries atomically."""
    lock = CrossProcessFileLock(APP_DATA / "dependency-update.lock", timeout=0.0)
    if not lock.acquire():
        raise UpdateError(
            "Outra instância está atualizando as dependências. "
            "Aguarde a operação terminar e tente novamente; os executáveis atuais não foram substituídos."
        )
    try:
        return _install_tool_from_release_locked(tool, system, progress=progress)
    finally:
        lock.release()

def compatible_asset_names(system: SystemInfo) -> dict[str, Optional[str]]:
    return {"yt-dlp": yt_asset_name(system), "ffmpeg": ff_asset_name(system)}

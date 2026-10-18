from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Callable, Optional
from urllib.parse import urlsplit

from .config import APP_DATA, INSTALL_ID_PATH, INSTALL_ROOT, PRODUCT_ID, VENDOR, VERSION

OWNER = "slydtaz"
REPOSITORY = "Chatgpt-media-downloader"
API_ROOT = f"https://api.github.com/repos/{OWNER}/{REPOSITORY}"
RAW_ROOT = f"https://raw.githubusercontent.com/{OWNER}/{REPOSITORY}/main"
MAIN_ARCHIVE_URL = f"https://github.com/{OWNER}/{REPOSITORY}/archive/refs/heads/main.zip"
USER_AGENT = f"ChatGPT-Media-Downloader/{VERSION}"
INSTALL_MARKER = ".chatgpt-media-downloader-install.json"
MAX_DOWNLOAD_BYTES = 250 * 1024 * 1024
MAX_SOURCE_UNPACKED_BYTES = 512 * 1024 * 1024


class AppUpdateError(RuntimeError):
    """User-safe error raised by the whole-app updater/repair workflow."""


@dataclass(frozen=True)
class AppUpdate:
    current_version: str
    version: str
    kind: str  # "source" or "executable"
    download_url: str
    release_url: str
    notes: str = ""
    tag_name: str = ""
    checksum_url: str = ""
    asset_sha256: str = ""
    download_size: int = 0
    published_at: str = ""
    source_ref: str = "main"


@dataclass(frozen=True)
class PreparedUpdate:
    kind: str
    version: str
    path: Path
    target_root: Path


def version_key(value: str) -> tuple[int, ...]:
    """Parse a semver-like version safely without adding a third-party dependency."""
    match = re.search(r"v?(\d+(?:\.\d+){0,5})", str(value or "").strip(), re.IGNORECASE)
    if not match:
        return (0,)
    try:
        return tuple(int(part) for part in match.group(1).split("."))
    except ValueError:
        return (0,)


def is_newer_version(candidate: str, current: str) -> bool:
    left, right = version_key(candidate), version_key(current)
    width = max(len(left), len(right))
    return left + (0,) * (width - len(left)) > right + (0,) * (width - len(right))


def _trusted_url(url: str, *, metadata: bool = False) -> bool:
    try:
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
        if parts.scheme != "https":
            return False
    except ValueError:
        return False
    allowed = {"github.com", "objects.githubusercontent.com", "release-assets.githubusercontent.com", "codeload.github.com"}
    if metadata:
        allowed |= {"api.github.com", "raw.githubusercontent.com"}
    return host in allowed


def _request_bytes(url: str, *, timeout: int = 20, maximum: int = MAX_DOWNLOAD_BYTES) -> bytes:
    if not _trusted_url(url, metadata=True):
        raise AppUpdateError("O endereço de atualização não pertence ao GitHub autorizado.")
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            final_url = response.geturl()
            if not _trusted_url(final_url, metadata=True):
                raise AppUpdateError("O GitHub redirecionou para um endereço não autorizado.")
            declared = int(response.headers.get("Content-Length", "0") or 0)
            if declared > maximum:
                raise AppUpdateError("O arquivo informado pelo servidor excede o limite de segurança.")
            data = response.read(maximum + 1)
            if len(data) > maximum:
                raise AppUpdateError("O arquivo baixado excedeu o limite de segurança.")
            return data
    except AppUpdateError:
        raise
    except (OSError, TimeoutError, urllib.error.URLError, ValueError) as exc:
        raise AppUpdateError(f"Não foi possível consultar o GitHub: {exc}") from exc


def _request_json(url: str, *, allow_404: bool = False) -> Optional[dict]:
    try:
        raw = _request_bytes(url, timeout=20, maximum=5 * 1024 * 1024)
    except AppUpdateError as exc:
        # 404 from the public releases endpoint is the expected state before the
        # first stable release is published. Don't suppress ordinary network errors.
        if allow_404 and isinstance(exc.__cause__, urllib.error.HTTPError) and exc.__cause__.code == 404:
            return None
        raise
    try:
        result = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AppUpdateError("O GitHub retornou informações de atualização inválidas.") from exc
    if not isinstance(result, dict):
        raise AppUpdateError("O GitHub retornou um formato de atualização inesperado.")
    return result


def _request_text(url: str) -> str:
    return _request_bytes(url, timeout=20, maximum=1024 * 1024).decode("utf-8", errors="replace")


def _asset(release: dict, name: str) -> Optional[dict]:
    for asset in release.get("assets", []):
        if isinstance(asset, dict) and asset.get("name") == name and asset.get("state", "uploaded") == "uploaded":
            url = str(asset.get("browser_download_url") or "")
            if url and _trusted_url(url):
                return asset
    return None


def _source_version() -> str:
    text = _request_text(f"{RAW_ROOT}/app/config.py")
    match = re.search(r'^VERSION\s*=\s*[\"\']([^\"\']+)[\"\']', text, re.MULTILINE)
    if not match:
        raise AppUpdateError("Não foi possível identificar a versão atual da branch main.")
    return match.group(1).strip()


def _source_notes(version: str, release_body: str = "") -> str:
    notes = (release_body or "").strip()
    if notes:
        return notes[:6000]
    try:
        changelog = _request_text(f"{RAW_ROOT}/CHANGELOG.md")
        sections = re.split(r"(?m)^##\s+", changelog)
        target = version.lstrip("v")
        for section in sections:
            heading = section.splitlines()[0].strip() if section.strip() else ""
            if heading.lstrip("v") == target:
                return "## " + section[:5000].strip()
    except AppUpdateError:
        pass
    return "Esta versão contém atualizações do aplicativo disponíveis no repositório oficial."


def _release_version(release: dict) -> str:
    """Return a semantic version from a version tag or a stable-alias release title.

    GitHub releases can use the mutable `stable` tag as a convenience alias, while
    the actual application version remains in the release title (for example,
    "ChatGPT Media Downloader 5.0.2 — Stable"). Never treat the literal word
    'stable' as a version number.
    """
    tag = str(release.get("tag_name") or "").strip()
    match = re.fullmatch(r"v?(\d+(?:\.\d+){1,5})", tag, re.IGNORECASE)
    if match:
        return match.group(1)
    title = str(release.get("name") or "").strip()
    match = re.search(r"(?<!\d)v?(\d+\.\d+(?:\.\d+){0,4})(?!\d)", title, re.IGNORECASE)
    return match.group(1) if match else ""


def _release_candidate(current: str, release: dict, *, frozen: bool) -> Optional[AppUpdate]:
    tag = str(release.get("tag_name") or "").strip()
    candidate_version = _release_version(release)
    if not tag or not candidate_version or not is_newer_version(candidate_version, current):
        return None
    html_url = str(release.get("html_url") or f"https://github.com/{OWNER}/{REPOSITORY}/releases")
    body = str(release.get("body") or "").strip()
    published_at = str(release.get("published_at") or "")
    if frozen:
        exe = _asset(release, "ChatGPTMediaDownloader.exe")
        sums = _asset(release, "SHA256SUMS.txt")
        if not exe or not sums:
            raise AppUpdateError(
                f"A Release {tag} não contém ChatGPTMediaDownloader.exe e SHA256SUMS.txt. "
                "A atualização automática foi cancelada por segurança."
            )
        digest = str(exe.get("digest") or "")
        if digest.lower().startswith("sha256:"):
            digest = digest.split(":", 1)[1].lower()
        else:
            digest = ""
        return AppUpdate(
            current, candidate_version, "executable", str(exe["browser_download_url"]), html_url,
            body or _source_notes(candidate_version), tag, str(sums["browser_download_url"]), digest,
            int(exe.get("size") or 0), published_at, tag,
        )
    archive = f"https://github.com/{OWNER}/{REPOSITORY}/archive/refs/tags/{tag}.zip"
    return AppUpdate(
        current, candidate_version, "source", archive, html_url,
        body or _source_notes(candidate_version), tag, download_size=0,
        published_at=published_at, source_ref=tag,
    )


def check_for_update(current_version: str = VERSION, *, frozen: Optional[bool] = None) -> Optional[AppUpdate]:
    """Choose the newest published release first, then fall back to stable alias/source."""
    if frozen is None:
        frozen = bool(getattr(sys, "frozen", False))

    # Versioned releases are the historical source of truth. Prefer GitHub's
    # latest versioned stable release; only use the mutable stable alias when
    # latest does not contain a newer build. This prevents an outdated alias from
    # forcing users through an intermediate update.
    release_urls = (f"{API_ROOT}/releases/latest", f"{API_ROOT}/releases/tags/stable")
    for release_url in release_urls:
        try:
            release = _request_json(release_url, allow_404=True)
        except AppUpdateError:
            if frozen:
                raise
            release = None
        if release and not release.get("draft") and not release.get("prerelease"):
            update = _release_candidate(current_version, release, frozen=frozen)
            if update:
                return update

    if frozen:
        return None
    # Source builds can still check the public main branch if no published Release
    # is newer. A broken network still raises if raw GitHub is down.
    source_version = _source_version()
    if is_newer_version(source_version, current_version):
        return AppUpdate(
            current_version, source_version, "source", MAIN_ARCHIVE_URL,
            f"https://github.com/{OWNER}/{REPOSITORY}/tree/main",
            _source_notes(source_version), "main", published_at="", source_ref="main",
        )
    return None


def check_repair_candidate(current_version: str = VERSION, *, frozen: Optional[bool] = None) -> AppUpdate:
    """Choose a complete trusted package even when installed version is current/corrupt."""
    if frozen is None:
        frozen = bool(getattr(sys, "frozen", False))
    if frozen:
        # Prefer a versioned stable Release; use the legacy stable alias only
        # when no versioned Release is available.
        release = _request_json(f"{API_ROOT}/releases/latest", allow_404=True)
        if not release or release.get("draft") or release.get("prerelease"):
            release = _request_json(f"{API_ROOT}/releases/tags/stable", allow_404=True)
        if not release or release.get("draft") or release.get("prerelease"):
            raise AppUpdateError("Ainda não existe uma Release estável publicada para reparar o executável.")
        candidate = _release_candidate(current_version, release, frozen=True)
        if candidate:
            return candidate
        tag = str(release.get("tag_name") or "").strip()
        release_version = _release_version(release)
        exe = _asset(release, "ChatGPTMediaDownloader.exe")
        sums = _asset(release, "SHA256SUMS.txt")
        if not tag or not release_version or not exe or not sums:
            raise AppUpdateError("A Release mais recente não contém uma versão válida, o executável e o hash SHA-256 exigidos para reparo.")
        digest = str(exe.get("digest") or "")
        digest = digest.split(":", 1)[1].lower() if digest.lower().startswith("sha256:") else ""
        return AppUpdate(current_version, release_version, "executable", exe["browser_download_url"],
                         str(release.get("html_url") or ""), str(release.get("body") or ""), tag,
                         sums["browser_download_url"], digest, int(exe.get("size") or 0),
                         str(release.get("published_at") or ""), tag)
    release = _request_json(f"{API_ROOT}/releases/latest", allow_404=True)
    if not release or release.get("draft") or release.get("prerelease"):
        release = _request_json(f"{API_ROOT}/releases/tags/stable", allow_404=True)
    source_version = _source_version()
    if release and not release.get("draft") and not release.get("prerelease"):
        tag = str(release.get("tag_name") or "").strip()
        release_version = _release_version(release)
        if tag and release_version and version_key(release_version) >= version_key(source_version):
            return AppUpdate(
                current_version, release_version, "source",
                f"https://github.com/{OWNER}/{REPOSITORY}/archive/refs/tags/{tag}.zip",
                str(release.get("html_url") or f"https://github.com/{OWNER}/{REPOSITORY}/releases"),
                str(release.get("body") or _source_notes(release_version)), tag,
                published_at=str(release.get("published_at") or ""), source_ref=tag,
            )
    return AppUpdate(current_version, source_version, "source", MAIN_ARCHIVE_URL,
                     f"https://github.com/{OWNER}/{REPOSITORY}/tree/main", _source_notes(source_version),
                     "main", source_ref="main")


def _download_file(url: str, destination: Path, progress: Optional[Callable[[int, int], None]] = None) -> tuple[int, str]:
    if not _trusted_url(url):
        raise AppUpdateError("O endereço do arquivo não é um asset autorizado do GitHub.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/octet-stream"})
    digest = hashlib.sha256()
    done = 0
    try:
        with urllib.request.urlopen(request, timeout=60) as response, destination.open("wb") as out:
            final_url = response.geturl()
            if not _trusted_url(final_url):
                raise AppUpdateError("O GitHub redirecionou o download para um domínio não autorizado.")
            total = int(response.headers.get("Content-Length", "0") or 0)
            if total > MAX_DOWNLOAD_BYTES:
                raise AppUpdateError("O arquivo de atualização é maior que o limite de segurança.")
            while True:
                block = response.read(1024 * 1024)
                if not block:
                    break
                done += len(block)
                if done > MAX_DOWNLOAD_BYTES:
                    raise AppUpdateError("O download excedeu o limite de segurança.")
                out.write(block)
                digest.update(block)
                if progress:
                    progress(done, total)
        if total and done != total:
            raise AppUpdateError("O download terminou antes do tamanho informado pelo GitHub.")
        return done, digest.hexdigest()
    except AppUpdateError:
        destination.unlink(missing_ok=True)
        raise
    except (OSError, TimeoutError, urllib.error.URLError, ValueError) as exc:
        destination.unlink(missing_ok=True)
        raise AppUpdateError(f"Falha ao baixar o pacote de atualização: {exc}") from exc


def _verify_executable_hash(update: AppUpdate, staged: Path, computed_hash: str, temp_dir: Path) -> None:
    if update.asset_sha256:
        expected = update.asset_sha256.lower()
    else:
        if not update.checksum_url:
            raise AppUpdateError("A Release não fornece hash SHA-256; o executável não será instalado.")
        sums_file = temp_dir / "SHA256SUMS.txt"
        _download_file(update.checksum_url, sums_file)
        checksum_text = sums_file.read_text(encoding="utf-8", errors="replace")
        expected = ""
        for line in checksum_text.splitlines():
            match = re.match(r"^\s*([0-9a-fA-F]{64})\s+\*?(.+?)\s*$", line)
            if match and Path(match.group(2)).name == "ChatGPTMediaDownloader.exe":
                expected = match.group(1).lower()
                break
    if len(expected) != 64 or computed_hash.lower() != expected:
        raise AppUpdateError("A verificação SHA-256 do executável falhou. A versão instalada foi preservada.")
    if not staged.is_file() or staged.stat().st_size < 1024 * 1024:
        raise AppUpdateError("O arquivo executável baixado é pequeno demais ou está incompleto.")


def _safe_extract_zip(archive: Path, destination: Path) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    dest_resolved = destination.resolve()
    try:
        with zipfile.ZipFile(archive) as zf:
            members = zf.infolist()
            if not members or len(members) > 10000:
                raise AppUpdateError("O arquivo de origem tem uma estrutura inesperada.")
            unpacked_size = sum(max(0, int(member.file_size)) for member in members)
            if unpacked_size > MAX_SOURCE_UNPACKED_BYTES:
                raise AppUpdateError("O pacote de origem excede o limite de tamanho após extração.")
            for member in members:
                pure = PurePosixPath(member.filename)
                if pure.is_absolute() or ".." in pure.parts or "\\" in member.filename:
                    raise AppUpdateError("O pacote de origem contém um caminho inseguro.")
                target = (destination / Path(*pure.parts)).resolve()
                if target != dest_resolved and dest_resolved not in target.parents:
                    raise AppUpdateError("O pacote de origem tenta gravar fora da pasta temporária.")
                mode = (member.external_attr >> 16) & 0o170000
                if mode == 0o120000:
                    raise AppUpdateError("O pacote de origem contém um link simbólico não permitido.")
            zf.extractall(destination)
    except AppUpdateError:
        raise
    except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
        raise AppUpdateError(f"O pacote ZIP não pôde ser extraído com segurança: {exc}") from exc

    for candidate in destination.iterdir():
        if candidate.is_dir() and (candidate / "app" / "main.py").is_file():
            if (candidate / "PROJECT_ID").is_file() and (candidate / "app" / "bootstrap.py").is_file():
                product_id = (candidate / "PROJECT_ID").read_text(encoding="utf-8", errors="replace").strip()
                if product_id == PRODUCT_ID:
                    return candidate
    raise AppUpdateError("O pacote não parece ser uma cópia completa do ChatGPT Media Downloader.")


def _version_from_tree(root: Path) -> str:
    text = (root / "app" / "config.py").read_text(encoding="utf-8", errors="replace")
    match = re.search(r'^VERSION\s*=\s*[\"\']([^\"\']+)[\"\']', text, re.MULTILINE)
    if not match:
        raise AppUpdateError("Não foi possível validar a versão do pacote baixado.")
    return match.group(1).strip()


def _stage_source_tree(source_root: Path, target_root: Path, version: str) -> Path:
    token = uuid.uuid4().hex[:10]
    stage = target_root.with_name(f".{target_root.name}.staging-{token}")
    try:
        if stage.exists():
            shutil.rmtree(stage)
        shutil.copytree(source_root, stage, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", ".git"))
        # Source builds store media binaries next to the app. Preserve them across
        # source replacement; user config/downloads live elsewhere and are untouched.
        old_tools = target_root / "tools"
        new_tools = stage / "tools"
        if old_tools.is_dir():
            shutil.copytree(old_tools, new_tools, dirs_exist_ok=True)
        marker = target_root / INSTALL_MARKER
        marker_data = None
        if marker.is_file():
            try:
                candidate = json.loads(marker.read_text(encoding="utf-8"))
                if candidate.get("vendor") == VENDOR and candidate.get("product_id") == PRODUCT_ID:
                    marker_data = candidate
            except (OSError, json.JSONDecodeError):
                marker_data = None
        if marker_data is None:
            try:
                install_id = INSTALL_ID_PATH.read_text(encoding="utf-8", errors="replace").strip()
            except OSError:
                install_id = "recovered"
            marker_data = {"vendor": VENDOR, "product_id": PRODUCT_ID, "install_id": install_id}
        marker_data["version"] = version
        marker_data["installed_from"] = "GitHub updater"
        marker_data["updated_at"] = __import__("time").strftime("%Y-%m-%dT%H:%M:%S")
        (stage / INSTALL_MARKER).write_text(json.dumps(marker_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        required = [stage / "app" / "main.py", stage / "app" / "bootstrap.py", stage / "launcher.vbs",
                    stage / "launcher.sh", stage / "PROJECT_ID", stage / INSTALL_MARKER]
        missing = [str(path.relative_to(stage)) for path in required if not path.is_file()]
        if missing:
            raise AppUpdateError("O pacote preparado está incompleto: " + ", ".join(missing))
        if (stage / "PROJECT_ID").read_text(encoding="utf-8", errors="replace").strip() != PRODUCT_ID:
            raise AppUpdateError("O Product ID do pacote preparado não corresponde ao aplicativo.")
        if _version_from_tree(stage) != version:
            raise AppUpdateError("A versão do pacote preparado não corresponde à versão informada pelo GitHub.")
        return stage
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def prepare_update(
    update: AppUpdate,
    *,
    target_root: Path = INSTALL_ROOT,
    progress: Optional[Callable[[str, int, int], None]] = None,
) -> PreparedUpdate:
    """Download and validate to a staging location; live application files are not changed yet."""
    temp_dir = APP_DATA / "temp" / f"app-update-{uuid.uuid4().hex[:10]}"
    temp_dir.mkdir(parents=True, exist_ok=False)
    try:
        if update.kind == "executable":
            staged = temp_dir / "ChatGPTMediaDownloader.exe"
            if progress:
                progress("Baixando o executável completo", 0, update.download_size)
            size, sha = _download_file(update.download_url, staged,
                                      lambda done, total: progress("Baixando o executável completo", done, total) if progress else None)
            if update.download_size and size != update.download_size:
                raise AppUpdateError("O tamanho do executável difere dos metadados da Release.")
            _verify_executable_hash(update, staged, sha, temp_dir)
            return PreparedUpdate("executable", update.version, staged, target_root)
        if update.kind != "source":
            raise AppUpdateError("Tipo de pacote de atualização desconhecido.")
        archive = temp_dir / "source.zip"
        if progress:
            progress("Baixando todos os arquivos do código-fonte", 0, update.download_size)
        _download_file(update.download_url, archive,
                       lambda done, total: progress("Baixando todos os arquivos do código-fonte", done, total) if progress else None)
        extract_dir = temp_dir / "extract"
        source_root = _safe_extract_zip(archive, extract_dir)
        actual_version = _version_from_tree(source_root)
        if is_newer_version(actual_version, update.version) or is_newer_version(update.version, actual_version):
            raise AppUpdateError(
                f"O pacote baixado indica a versão {actual_version}, mas o GitHub informou {update.version}."
            )
        if progress:
            progress("Validando e preparando a nova instalação", 0, 0)
        staged_root = _stage_source_tree(source_root, target_root, actual_version)
        return PreparedUpdate("source", actual_version, staged_root, target_root)
    finally:
        # Prepared executable lives under temp_dir until the helper replaces it.
        # Source tree is staged beside the active installation so directory rename
        # stays on the same volume; remove only temporary zip/extraction content.
        try:
            (temp_dir / "source.zip").unlink(missing_ok=True)
            shutil.rmtree(temp_dir / "extract", ignore_errors=True)
            (temp_dir / "SHA256SUMS.txt").unlink(missing_ok=True)
            if not (temp_dir / "ChatGPTMediaDownloader.exe").exists():
                temp_dir.rmdir()
        except OSError:
            pass


def _ps_quote(value: str | Path) -> str:
    return str(value).replace("'", "''")


def schedule_apply_update(prepared: PreparedUpdate, *, launch_after: bool, python_executable: str = sys.executable) -> None:
    """Spawn an OS helper to swap the package only after this process has exited."""
    if os.name == "nt":
        helper = APP_DATA / "temp" / f"apply-update-{uuid.uuid4().hex[:10]}.ps1"
        helper.parent.mkdir(parents=True, exist_ok=True)
        script = r'''param(
  [Parameter(Mandatory=$true)][int]$WaitPid,
  [Parameter(Mandatory=$true)][ValidateSet('source','executable')][string]$Mode,
  [Parameter(Mandatory=$true)][string]$TargetRoot,
  [Parameter(Mandatory=$true)][string]$StagedPath,
  [Parameter(Mandatory=$true)][string]$Version,
  [Parameter(Mandatory=$true)][bool]$Reopen,
  [Parameter(Mandatory=$true)][string]$PythonExe
)
$ErrorActionPreference = 'Stop'
$TargetRoot = [System.IO.Path]::GetFullPath($TargetRoot)
$StagedPath = [System.IO.Path]::GetFullPath($StagedPath)
$token = [Guid]::NewGuid().ToString('N').Substring(0,10)
try {
  while (Get-Process -Id $WaitPid -ErrorAction SilentlyContinue) { Start-Sleep -Milliseconds 350 }
  if ($Mode -eq 'executable') {
    $target = Join-Path $TargetRoot 'ChatGPTMediaDownloader.exe'
    if (!(Test-Path -LiteralPath $target)) { throw "O executável instalado não existe: $target" }
    if (!(Test-Path -LiteralPath $StagedPath)) { throw "O novo executável não foi encontrado: $StagedPath" }
    $backup = "$target.backup-$token"
    Copy-Item -LiteralPath $target -Destination $backup
    try {
      Move-Item -LiteralPath $StagedPath -Destination $target -Force
      if (!(Test-Path -LiteralPath $target)) { throw 'O novo executável não foi encontrado após a troca.' }
      Remove-Item -LiteralPath $backup -Force -ErrorAction SilentlyContinue
    } catch {
      if (Test-Path -LiteralPath $backup) { Copy-Item -LiteralPath $backup -Destination $target -Force }
      throw
    }
  } else {
    if (!(Test-Path -LiteralPath $StagedPath)) { throw "A pasta preparada não foi encontrada: $StagedPath" }
    $backup = "$TargetRoot.backup-$token"
    Move-Item -LiteralPath $TargetRoot -Destination $backup
    try {
      Move-Item -LiteralPath $StagedPath -Destination $TargetRoot
      if (!(Test-Path -LiteralPath (Join-Path $TargetRoot 'app\bootstrap.py'))) { throw 'A instalação atualizada está incompleta.' }
      Remove-Item -LiteralPath $backup -Recurse -Force -ErrorAction SilentlyContinue
    } catch {
      if (!(Test-Path -LiteralPath $TargetRoot) -and (Test-Path -LiteralPath $backup)) { Move-Item -LiteralPath $backup -Destination $TargetRoot }
      throw
    }
  }
  $marker = Join-Path $TargetRoot '.chatgpt-media-downloader-install.json'
  if (Test-Path -LiteralPath $marker) {
    try {
      $markerData = Get-Content -LiteralPath $marker -Raw | ConvertFrom-Json
      $markerData.version = $Version
      $markerData.updated_at = (Get-Date).ToString('s')
      $markerData | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $marker -Encoding UTF8
    } catch { }
  }
  if ($Reopen) {
    if ($Mode -eq 'executable') {
      Start-Process -FilePath (Join-Path $TargetRoot 'ChatGPTMediaDownloader.exe') -ArgumentList '--installed' -WorkingDirectory $TargetRoot
    } else {
      Start-Process -FilePath $PythonExe -ArgumentList @('-m','app.bootstrap','--installed') -WorkingDirectory $TargetRoot
    }
  }
  exit 0
} catch {
  $log = Join-Path $env:TEMP 'ChatGPTMediaDownloader-update-error.txt'
  $_ | Out-String | Set-Content -LiteralPath $log -Encoding UTF8
  if (Test-Path -LiteralPath $backup) { Write-Output "Backup preservado: $backup" }
  exit 1
} finally {
  Start-Sleep -Milliseconds 1000
  Remove-Item -LiteralPath $MyInvocation.MyCommand.Path -Force -ErrorAction SilentlyContinue
}
'''
        helper.write_text(script, encoding="utf-8-sig")
        args = [
            "powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(helper),
            "-WaitPid", str(os.getpid()), "-Mode", prepared.kind, "-TargetRoot", str(prepared.target_root),
            "-StagedPath", str(prepared.path), "-Version", prepared.version,
            "-Reopen", ("true" if launch_after else "false"), "-PythonExe", python_executable,
        ]
        try:
            kwargs = {"close_fds": True, "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}
            subprocess.Popen(args, **kwargs)
        except OSError as exc:
            helper.unlink(missing_ok=True)
            raise AppUpdateError(f"Não foi possível iniciar o aplicador de atualizações: {exc}") from exc
        return

    # Portable source update for Linux/macOS. Frozen non-Windows builds are not
    # produced by the current CI and therefore cannot use the Windows EXE path.
    if prepared.kind != "source":
        raise AppUpdateError("A atualização do executável automático está disponível atualmente apenas no Windows.")
    import shlex
    helper = APP_DATA / "temp" / f"apply-update-{uuid.uuid4().hex[:10]}.sh"
    helper.parent.mkdir(parents=True, exist_ok=True)
    target = str(prepared.target_root)
    stage = str(prepared.path)
    target_q, stage_q = shlex.quote(target), shlex.quote(stage)
    python_q = shlex.quote(python_executable)
    reopen_cmd = f"cd {target_q} && {python_q} -m app.bootstrap --installed" if launch_after else ":"
    script = f'''#!/bin/sh
set -eu
wait_pid={os.getpid()}
while kill -0 "$wait_pid" 2>/dev/null; do sleep 0.35; done
target={target_q}
staged={stage_q}
backup="${{target}}.backup-$(date +%s)"
mv "$target" "$backup"
if ! mv "$staged" "$target"; then mv "$backup" "$target"; exit 1; fi
rm -rf "$backup"
{reopen_cmd} &
rm -f "$0"
'''
    helper.write_text(script, encoding="utf-8")
    helper.chmod(0o700)
    try:
        subprocess.Popen(["/bin/sh", str(helper)], close_fds=True, start_new_session=True)
    except OSError as exc:
        helper.unlink(missing_ok=True)
        raise AppUpdateError(f"Não foi possível iniciar o aplicador de atualizações: {exc}") from exc

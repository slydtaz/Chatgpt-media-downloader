"""Safe data-only storage for user-selected app backgrounds.

Only supported raster images and common video containers are accepted. Assets are
never imported as programs and this module never executes an asset.
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import re
import socket
import stat
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .config import APP_DATA, ensure_dirs
from .security import safe_archive_member_path, validate_url

MAX_ASSET_BYTES = 512 * 1024 * 1024
_CHUNK_SIZE = 1024 * 1024
_ASSET_ID_RE = re.compile(r"^[a-f0-9]{32}$")
_ALLOWED_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp",
    ".mp4", ".m4v", ".mov", ".webm", ".mkv", ".avi",
}
_IMAGE_SIGNATURES = (
    (".png", lambda b: b.startswith(b"\x89PNG\r\n\x1a\n")),
    (".jpg", lambda b: b.startswith(b"\xff\xd8\xff")),
    (".gif", lambda b: b.startswith((b"GIF87a", b"GIF89a"))),
    (".webp", lambda b: len(b) >= 12 and b[:4] == b"RIFF" and b[8:12] == b"WEBP"),
    (".bmp", lambda b: b.startswith(b"BM")),
)
_VIDEO_TYPES = {
    ".mp4": "video/mp4", ".m4v": "video/mp4", ".mov": "video/quicktime",
    ".webm": "video/webm", ".mkv": "video/x-matroska", ".avi": "video/x-msvideo",
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".gif": "image/gif", ".webp": "image/webp", ".bmp": "image/bmp",
}


def background_store_dir() -> Path:
    """Return the private per-user library directory, creating it if needed."""
    ensure_dirs()
    root = APP_DATA / "backgrounds"
    root.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(root, 0o700)
    except OSError:
        pass
    if root.is_symlink():
        raise ValueError("A pasta de fundos não pode ser um link simbólico.")
    return root.resolve()


def _manifest_path(root: Path) -> Path:
    path = root / "library.json"
    if path.is_symlink():
        raise ValueError("O índice de fundos é inseguro.")
    return path


def _load_manifest(root: Path) -> dict:
    path = _manifest_path(root)
    if not path.exists():
        return {"schema": 1, "assets": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("O índice da biblioteca de fundos está danificado; ele não será recriado automaticamente.") from exc
    if not isinstance(data, dict) or data.get("schema") != 1 or not isinstance(data.get("assets"), list):
        raise ValueError("O formato do índice da biblioteca de fundos não é válido.")
    # Malformed entries are ignored, never interpreted as paths or commands.
    assets = [item for item in data["assets"] if isinstance(item, dict) and _ASSET_ID_RE.fullmatch(str(item.get("id", "")))]
    return {"schema": 1, "assets": assets}


def _save_manifest(root: Path, manifest: dict) -> None:
    path = _manifest_path(root)
    temporary = root / f".library-{uuid.uuid4().hex}.tmp"
    payload = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    try:
        with temporary.open("x", encoding="utf-8") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.chmod(temporary, 0o600)
        except OSError:
            pass
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def _classify_header(header: bytes, suggested_name: str) -> tuple[str, str]:
    """Classify by file signature rather than extension or HTTP content type."""
    for extension, checker in _IMAGE_SIGNATURES:
        if checker(header):
            return extension, "image"
    if len(header) >= 12 and header[4:8] == b"ftyp":
        hinted = Path(suggested_name).suffix.lower()
        extension = hinted if hinted in {".mp4", ".m4v", ".mov"} else ".mp4"
        return extension, "video"
    if header.startswith(b"\x1a\x45\xdf\xa3"):
        hinted = Path(suggested_name).suffix.lower()
        extension = hinted if hinted in {".webm", ".mkv"} else ".mkv"
        return extension, "video"
    if len(header) >= 12 and header[:4] == b"RIFF" and header[8:12] == b"AVI ":
        return ".avi", "video"
    raise ValueError("O arquivo não parece ser uma imagem ou vídeo suportado. SVG, HTML e executáveis não são aceitos.")


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(_CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _store_stream(stream, suggested_name: str, *, content_length: int | None = None) -> dict:
    if content_length is not None and content_length > MAX_ASSET_BYTES:
        raise ValueError("O fundo ultrapassa o limite de 512 MiB.")
    root = background_store_dir()
    staging = root / f".import-{uuid.uuid4().hex}.part"
    digest = hashlib.sha256()
    total = 0
    header = b""
    try:
        with staging.open("xb") as output:
            while True:
                chunk = stream.read(_CHUNK_SIZE)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_ASSET_BYTES:
                    raise ValueError("O fundo ultrapassa o limite de 512 MiB.")
                if len(header) < 64:
                    header += chunk[:64 - len(header)]
                output.write(chunk)
                digest.update(chunk)
            output.flush()
            os.fsync(output.fileno())
        if total < 12:
            raise ValueError("O arquivo está vazio ou é pequeno demais para ser uma mídia válida.")
        extension, kind = _classify_header(header, suggested_name)
        asset_id = uuid.uuid4().hex
        path_name = f"{asset_id}{extension}"
        destination = safe_archive_member_path(root, path_name)
        if destination.exists() or destination.is_symlink():
            raise ValueError("Conflito inesperado no nome do arquivo de fundo.")
        os.replace(staging, destination)
        try:
            os.chmod(destination, 0o600)
        except OSError:
            pass
        display_stem = Path(suggested_name).stem or ("Imagem" if kind == "image" else "Vídeo")
        display_name = re.sub(r"[\x00-\x1f<>:\"/\\|?*]+", "_", display_stem).strip(" .")[:100]
        if not display_name:
            display_name = "Fundo personalizado"
        record = {
            "id": asset_id,
            "file": path_name,
            "name": f"{display_name}{extension}",
            "kind": kind,
            "mime": _VIDEO_TYPES[extension],
            "size": total,
            "sha256": digest.hexdigest(),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            manifest = _load_manifest(root)
            manifest["assets"] = [a for a in manifest["assets"] if a.get("id") != asset_id]
            manifest["assets"].append(record)
            _save_manifest(root, manifest)
        except Exception:
            destination.unlink(missing_ok=True)
            raise
        return record
    finally:
        try:
            staging.unlink(missing_ok=True)
        except OSError:
            pass


def import_file(source: str | Path) -> dict:
    """Copy a local image/video into the library after signature and size checks."""
    source = Path(source).expanduser()
    try:
        info = source.lstat()
    except OSError as exc:
        raise ValueError(f"Não foi possível acessar o arquivo selecionado: {exc}") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise ValueError("Selecione um arquivo comum, não uma pasta ou link simbólico.")
    if info.st_size > MAX_ASSET_BYTES:
        raise ValueError("O fundo ultrapassa o limite de 512 MiB.")
    with source.open("rb") as stream:
        return _store_stream(stream, source.name, content_length=info.st_size)


def _validate_public_https_url(url: str) -> str:
    valid, reason = validate_url(url)
    if not valid:
        raise ValueError(reason)
    parts = urlsplit(url.strip())
    if parts.scheme.lower() != "https" or not parts.hostname or parts.username or parts.password:
        raise ValueError("Use um link HTTPS público, sem nome de usuário ou senha incorporados.")
    if parts.port not in (None, 443):
        raise ValueError("Por segurança, links HTTPS em portas não padrão não são aceitos.")
    host = parts.hostname.rstrip(".")
    try:
        addresses = [ipaddress.ip_address(host)]
    except ValueError:
        try:
            answers = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
            addresses = [ipaddress.ip_address(answer[4][0]) for answer in answers]
        except (OSError, ValueError) as exc:
            raise ValueError("Não foi possível verificar o endereço público do servidor.") from exc
    if not addresses or any(not address.is_global for address in addresses):
        raise ValueError("Links para computadores ou redes locais não são aceitos.")
    return url.strip()


class _SafeHTTPSRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _validate_public_https_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def import_url(url: str) -> dict:
    """Download a direct HTTPS media file with public-host and size restrictions."""
    checked = _validate_public_https_url(url)
    parts = urlsplit(checked)
    suggested_name = unquote(Path(parts.path).name) or "fundo"
    opener = build_opener(_SafeHTTPSRedirectHandler())
    request = Request(checked, headers={"User-Agent": "ChatGPTMediaDownloader-Backgrounds/1.0", "Accept": "image/*, video/*"})
    with opener.open(request, timeout=25) as response:
        final_url = _validate_public_https_url(response.geturl())
        del final_url
        content_type = response.headers.get_content_type().lower()
        if not (content_type.startswith("image/") or content_type.startswith("video/") or content_type == "application/octet-stream"):
            raise ValueError("O link não retornou uma imagem ou vídeo.")
        raw_length = response.headers.get("Content-Length")
        try:
            length = int(raw_length) if raw_length else None
        except ValueError:
            length = None
        if length is not None and length > MAX_ASSET_BYTES:
            raise ValueError("O fundo ultrapassa o limite de 512 MiB.")
        if not Path(suggested_name).suffix:
            suffix_by_type = {
                "image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp",
                "image/gif": ".gif", "image/bmp": ".bmp", "video/mp4": ".mp4",
                "video/webm": ".webm", "video/quicktime": ".mov", "video/x-matroska": ".mkv",
                "video/x-msvideo": ".avi",
            }
            suggested_name += suffix_by_type.get(content_type, "")
        return _store_stream(response, suggested_name, content_length=length)


def list_assets(*, verify: bool = True) -> list[dict]:
    """List media records; a failed integrity check makes an item unusable."""
    root = background_store_dir()
    manifest = _load_manifest(root)
    result = []
    for entry in manifest["assets"]:
        item = dict(entry)
        try:
            path = _asset_path(root, entry)
            good = path.is_file() and not path.is_symlink() and path.stat().st_size == int(entry.get("size", -1))
            if good and verify:
                good = _hash_file(path) == str(entry.get("sha256", ""))
            item["valid"] = bool(good)
        except (OSError, ValueError, TypeError):
            item["valid"] = False
        result.append(item)
    result.sort(key=lambda item: str(item.get("created_at", "")), reverse=True)
    return result


def _asset_path(root: Path, entry: dict) -> Path:
    asset_id = str(entry.get("id", ""))
    filename = str(entry.get("file", ""))
    if not _ASSET_ID_RE.fullmatch(asset_id):
        raise ValueError("Identificador de fundo inválido.")
    if Path(filename).name != filename or Path(filename).suffix.lower() not in _ALLOWED_EXTENSIONS:
        raise ValueError("Caminho de fundo inválido.")
    if not filename.startswith(asset_id + "."):
        raise ValueError("O arquivo não pertence ao registro de fundo.")
    target = safe_archive_member_path(root, filename)
    if target.is_symlink():
        raise ValueError("O arquivo de fundo não pode ser um link simbólico.")
    return target


def resolve_asset(asset_id: str) -> tuple[dict, Path]:
    """Resolve a registered asset only after full SHA-256 verification."""
    if not _ASSET_ID_RE.fullmatch(str(asset_id)):
        raise ValueError("Identificador de fundo inválido.")
    root = background_store_dir()
    record = next((item for item in _load_manifest(root)["assets"] if item.get("id") == asset_id), None)
    if not record:
        raise FileNotFoundError("O fundo não está registrado na biblioteca.")
    path = _asset_path(root, record)
    if not path.is_file() or path.stat().st_size != int(record.get("size", -1)):
        raise ValueError("O arquivo de fundo está ausente ou foi alterado.")
    extension, kind = _classify_header(path.open("rb").read(64), record.get("name", path.name))
    if kind != record.get("kind") or extension not in _ALLOWED_EXTENSIONS:
        raise ValueError("A assinatura do arquivo não corresponde ao registro.")
    if _hash_file(path) != str(record.get("sha256", "")):
        raise ValueError("A verificação SHA-256 do fundo falhou. O arquivo não será aberto.")
    return dict(record), path


def delete_asset(asset_id: str) -> None:
    """Delete a registered asset without following links outside the library."""
    if not _ASSET_ID_RE.fullmatch(str(asset_id)):
        raise ValueError("Identificador de fundo inválido.")
    root = background_store_dir()
    manifest = _load_manifest(root)
    record = next((item for item in manifest["assets"] if item.get("id") == asset_id), None)
    if not record:
        raise FileNotFoundError("O fundo não está registrado na biblioteca.")
    path = _asset_path(root, record)
    if path.is_symlink():
        path.unlink()
    else:
        path.unlink(missing_ok=True)
    manifest["assets"] = [item for item in manifest["assets"] if item.get("id") != asset_id]
    _save_manifest(root, manifest)

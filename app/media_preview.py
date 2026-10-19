from __future__ import annotations

import ipaddress
import json
import socket
import ssl
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from .process_utils import hidden_subprocess_kwargs
from .security import redact_sensitive, validate_url

MAX_THUMBNAIL_BYTES = 5 * 1024 * 1024
_MAX_IMAGE_PIXELS = 25_000_000
_LOCAL_SUFFIXES = (".localhost", ".local", ".internal", ".test", ".invalid")


@dataclass(frozen=True)
class MediaPreview:
    url: str
    title: str
    creator: str = ""
    duration: float | None = None
    thumbnail_url: str = ""
    thumbnail_bytes: bytes | None = None


def _parsed_url(url: str):
    if not isinstance(url, str) or not url.strip():
        return None
    valid, _message = validate_url(url)
    if not valid:
        return None
    try:
        parsed = urlsplit(url.strip())
        host = (parsed.hostname or "").rstrip(".").lower()
        port = parsed.port
    except ValueError:
        return None
    if not host or parsed.username is not None or parsed.password is not None:
        return None
    if parsed.scheme.lower() not in {"http", "https"}:
        return None
    allowed_port = 443 if parsed.scheme.lower() == "https" else 80
    if port not in (None, allowed_port):
        return None
    if host == "localhost" or host.endswith(_LOCAL_SUFFIXES) or "." not in host:
        return None
    return parsed, host, (port or allowed_port)


def _host_is_public(host: str, port: int, *, resolve_dns: bool) -> bool:
    try:
        address = ipaddress.ip_address(host)
        return bool(address.is_global)
    except ValueError:
        pass
    if not resolve_dns:
        return True
    try:
        records = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except (OSError, socket.gaierror):
        return False
    addresses: set[str] = set()
    for record in records:
        try:
            addresses.add(str(ipaddress.ip_address(record[4][0])))
        except (ValueError, IndexError, TypeError):
            return False
    return bool(addresses) and all(ipaddress.ip_address(item).is_global for item in addresses)


def is_safe_media_url(url: str, *, resolve_dns: bool = True) -> bool:
    """Validate a public media page URL before invoking the metadata extractor."""
    parsed_info = _parsed_url(url)
    if not parsed_info:
        return False
    parsed, host, port = parsed_info
    return _host_is_public(host, port, resolve_dns=resolve_dns)


def is_safe_thumbnail_url(url: str, *, resolve_dns: bool = True) -> bool:
    """Allow only public HTTPS image URLs and ordinary TLS ports."""
    parsed_info = _parsed_url(url)
    if not parsed_info:
        return False
    parsed, host, port = parsed_info
    if parsed.scheme.lower() != "https" or port != 443:
        return False
    return _host_is_public(host, port, resolve_dns=resolve_dns)


def _thumbnail_candidates(payload: dict[str, Any]) -> list[str]:
    candidates: list[tuple[int, str]] = []
    direct = payload.get("thumbnail")
    if isinstance(direct, str) and direct:
        candidates.append((0, direct))
    thumbnails = payload.get("thumbnails")
    if isinstance(thumbnails, list):
        for item in thumbnails:
            if not isinstance(item, dict):
                continue
            url = item.get("url")
            if not isinstance(url, str) or not url:
                continue
            try:
                width = max(0, int(item.get("width") or 0))
                height = max(0, int(item.get("height") or 0))
            except (TypeError, ValueError, OverflowError):
                width = height = 0
            candidates.append((width * height, url))
    candidates.sort(key=lambda pair: pair[0], reverse=True)
    result: list[str] = []
    seen: set[str] = set()
    for _area, url in candidates:
        if url not in seen and is_safe_thumbnail_url(url, resolve_dns=False):
            seen.add(url)
            result.append(url)
    return result


def choose_thumbnail_url(payload: dict[str, Any], source_url: str = "") -> str:
    """Pick the largest safe supplied thumbnail, with a guarded YouTube fallback."""
    candidates = _thumbnail_candidates(payload)
    if candidates:
        return candidates[0]
    video_id = payload.get("id")
    extractor = str(payload.get("extractor_key") or payload.get("extractor") or "").lower()
    source_host = (urlsplit(source_url).hostname or "").lower()
    is_youtube = (
        "youtube" in extractor
        or source_host.endswith(("youtube.com", "youtube-nocookie.com", "youtu.be"))
    )
    if is_youtube and isinstance(video_id, str) and len(video_id) == 11 and all(
        char.isalnum() or char in "_-" for char in video_id
    ):
        fallback = f"https://i.ytimg.com/vi/{video_id}/mqdefault.jpg"
        return fallback if is_safe_thumbnail_url(fallback, resolve_dns=False) else ""
    return ""


def _parse_payload(stdout: str) -> dict[str, Any] | None:
    text = (stdout or "").strip()
    if not text:
        return None
    try:
        payload = json.loads(text)
        return payload if isinstance(payload, dict) else None
    except json.JSONDecodeError:
        pass
    for line in reversed(text.splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and ("title" in payload or "id" in payload):
            return payload
    return None


class _SafeThumbnailRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not is_safe_thumbnail_url(newurl, resolve_dns=True):
            raise urllib.error.HTTPError(
                req.full_url, code, "Redirecionamento de thumbnail bloqueado", headers, fp
            )
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_thumbnail_bytes(url: str, *, timeout: float = 6.0) -> bytes | None:
    """Fetch a small, public HTTPS poster only; never follows unsafe redirects."""
    if not is_safe_thumbnail_url(url, resolve_dns=True):
        return None
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "ChatGPT-Media-Downloader/5.3.2 (thumbnail preview)",
            "Accept": "image/avif,image/webp,image/png,image/jpeg,image/gif;q=0.9,*/*;q=0.1",
        },
        method="GET",
    )
    opener = urllib.request.build_opener(
        _SafeThumbnailRedirectHandler(),
        urllib.request.HTTPSHandler(context=ssl.create_default_context()),
    )
    try:
        with opener.open(request, timeout=timeout) as response:
            final_url = response.geturl()
            if not is_safe_thumbnail_url(final_url, resolve_dns=True):
                return None
            content_type = str(response.headers.get("Content-Type", "")).split(";", 1)[0].strip().lower()
            if content_type and not content_type.startswith("image/"):
                return None
            raw_length = response.headers.get("Content-Length")
            if raw_length:
                try:
                    if int(raw_length) > MAX_THUMBNAIL_BYTES:
                        return None
                except (ValueError, TypeError):
                    return None
            data = response.read(MAX_THUMBNAIL_BYTES + 1)
            if not data or len(data) > MAX_THUMBNAIL_BYTES:
                return None
            return data
    except (OSError, ValueError, TimeoutError, urllib.error.URLError, ssl.SSLError):
        return None


def inspect_media_preview(
    yt_dlp_path: str,
    url: str,
    *,
    timeout: float = 30.0,
    fetch_thumbnail: bool = True,
) -> MediaPreview:
    """Resolve one public page's metadata with yt-dlp; skip media downloads entirely."""
    valid, message = validate_url(url)
    if not valid:
        raise ValueError(message)
    if not is_safe_media_url(url, resolve_dns=True):
        raise ValueError("A prévia aceita somente URLs públicas HTTP/HTTPS em portas padrão.")
    command = [
        str(yt_dlp_path),
        "--ignore-config",
        "--dump-single-json",
        "--skip-download",
        "--no-playlist",
        "--no-warnings",
        "--no-progress",
        "--no-call-home",
        "--socket-timeout",
        "8",
        "--extractor-retries",
        "1",
        url,
    ]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
            **hidden_subprocess_kwargs(),
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("A prévia demorou demais. Confira o link e tente novamente.") from exc
    payload = _parse_payload(completed.stdout or "")
    if completed.returncode != 0 or payload is None:
        detail = redact_sensitive((completed.stderr or completed.stdout or "").strip())
        if detail:
            detail = detail[-600:]
        raise RuntimeError(detail or "O site não forneceu metadados suficientes para a prévia.")
    title = str(payload.get("title") or payload.get("fulltitle") or "Mídia sem título").strip()
    creator = str(
        payload.get("uploader")
        or payload.get("channel")
        or payload.get("creator")
        or payload.get("artist")
        or ""
    ).strip()
    try:
        raw_duration = payload.get("duration")
        duration = float(raw_duration) if raw_duration is not None else None
        if duration is not None and (duration < 0 or duration > 7 * 24 * 60 * 60):
            duration = None
    except (TypeError, ValueError, OverflowError):
        duration = None
    thumbnail_url = choose_thumbnail_url(payload, url)
    thumbnail_bytes = fetch_thumbnail_bytes(thumbnail_url) if fetch_thumbnail and thumbnail_url else None
    return MediaPreview(
        url=url,
        title=title[:500],
        creator=creator[:240],
        duration=duration,
        thumbnail_url=thumbnail_url,
        thumbnail_bytes=thumbnail_bytes,
    )

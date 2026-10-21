from __future__ import annotations

import ipaddress
import os
import re
from pathlib import Path
from urllib.parse import urlsplit
import urllib.error
import urllib.request


SENSITIVE_QUERY_KEYS = re.compile(
    r"(?i)(?:token|access_token|auth|authorization|password|passwd|secret|sig|signature|"
    r"credential|cookie|session|apikey|api_key|key)=([^&#\s]+)"
)
_HOST_LABEL = re.compile(r"^[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$")


def validate_url(url: str) -> tuple[bool, str]:
    """Accept only ordinary HTTP(S) URLs with a valid authority and no embedded credentials."""
    if not isinstance(url, str):
        return False, "URL inválida."
    value = url.strip()
    if not value:
        return False, "URL vazia."
    if any(ord(char) < 32 or ord(char) == 127 or char.isspace() for char in value):
        return False, "A URL contém espaços ou caracteres de controle."
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError:
        return False, "URL inválida."
    if parsed.scheme.lower() not in {"http", "https"}:
        return False, "Use uma URL HTTP ou HTTPS."
    if not parsed.netloc or not hostname:
        return False, "URL inválida: domínio ausente."
    if parsed.username is not None or parsed.password is not None:
        return False, "Não inclua usuário ou senha na URL."
    if port is not None and not 1 <= port <= 65535:
        return False, "Porta inválida na URL."

    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        try:
            ascii_host = hostname.rstrip(".").encode("idna").decode("ascii")
        except UnicodeError:
            return False, "Domínio inválido na URL."
        labels = ascii_host.split(".")
        if not ascii_host or len(ascii_host) > 253 or any(not _HOST_LABEL.fullmatch(part) for part in labels):
            return False, "Domínio inválido na URL."
    return True, ""


def redacted_url(url: str) -> str:
    """Return only the origin of a URL; never persist paths, query strings, or userinfo."""
    value = str(url or "").strip()
    try:
        parsed = urlsplit(value)
        host = parsed.hostname
        if not host:
            return "<URL>"
        port = parsed.port
        host_display = f"[{host}]" if ":" in host else host
        if port is not None:
            host_display = f"{host_display}:{port}"
        scheme = parsed.scheme.lower()
        if scheme not in {"http", "https"}:
            return "<URL omitida>"
        return f"{scheme}://{host_display}/<url-omitida>"
    except ValueError:
        return "<URL inválida>"


def redact_sensitive(text: str) -> str:
    if not text:
        return ""
    value = SENSITIVE_QUERY_KEYS.sub(lambda m: m.group(0).split("=")[0] + "=<redigido>", str(text))
    # Avoid persisting full URLs that may include signed query strings or credentials.
    value = re.sub(r"https?://[^\s]+", lambda m: redacted_url(m.group(0)), value)
    value = re.sub(r"(?i)(cookie|authorization|proxy-password|password)\s*[:=]\s*\S+", r"\1=<redigido>", value)
    return value



def _is_trusted_https_url(url: str, allowed_hosts: set[str] | frozenset[str]) -> bool:
    """Validate HTTPS, exact hostname, port and absence of userinfo."""
    try:
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
        port = parts.port
    except (TypeError, ValueError):
        return False
    return (
        parts.scheme.lower() == "https"
        and bool(host)
        and host in {str(item).lower() for item in allowed_hosts}
        and parts.username is None
        and parts.password is None
        and port in {None, 443}
    )


class RestrictedHTTPSRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Reject a redirect before urllib sends the next request."""

    def __init__(self, allowed_hosts: set[str] | frozenset[str]):
        super().__init__()
        self.allowed_hosts = frozenset(str(item).lower() for item in allowed_hosts)

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not _is_trusted_https_url(newurl, self.allowed_hosts):
            raise urllib.error.HTTPError(
                req.full_url,
                code,
                "Redirecionamento para endereço não autorizado bloqueado",
                headers,
                fp,
            )
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def trusted_urlopen(
    request: str | urllib.request.Request,
    *,
    allowed_hosts: set[str] | frozenset[str],
    timeout: int = 30,
):
    """Open HTTPS only, enforcing the allowlist before each redirect hop."""
    url = request.full_url if isinstance(request, urllib.request.Request) else str(request)
    if not _is_trusted_https_url(url, allowed_hosts):
        raise urllib.error.URLError("Endereço HTTPS fora da lista de hosts autorizados.")
    opener = urllib.request.build_opener(RestrictedHTTPSRedirectHandler(allowed_hosts))
    return opener.open(request, timeout=timeout)


def safe_archive_member_path(root: Path, member_name: str) -> Path:
    """Resolve a portable archive member beneath root and reject traversal/Windows ADS names."""
    if not isinstance(member_name, str):
        raise ValueError("Arquivo compactado contém caminho inseguro.")
    raw = member_name
    if not raw or "\x00" in raw or any(ord(char) < 32 or ord(char) == 127 for char in raw):
        raise ValueError("Arquivo compactado contém caminho inseguro.")
    if "\\" in raw:
        raise ValueError("Arquivo compactado contém separador de caminho ambíguo.")
    normalized = raw
    # Archive directory names commonly end in one slash; do not otherwise
    # normalize empty or dot components away before validating them.
    if normalized.endswith("/"):
        normalized = normalized[:-1]
    if not normalized or normalized.startswith("/") or re.match(r"^[a-zA-Z]:", normalized):
        raise ValueError("Arquivo compactado contém caminho inseguro.")
    parts = normalized.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError("Arquivo compactado contém caminho inseguro.")
    for part in parts:
        # Reject alternate data streams, invalid Windows separators/names, and
        # reserved device names even when extracting on a non-Windows host.
        if any(char in part for char in '<>:"|?*') or part.endswith((" ", ".")):
            raise ValueError("Arquivo compactado contém nome de arquivo inseguro.")
        device_stem = part.split(".", 1)[0].rstrip(" .").upper()
        if (device_stem in {"CON", "PRN", "AUX", "NUL"}
                or re.fullmatch(r"COM[1-9]", device_stem)
                or re.fullmatch(r"LPT[1-9]", device_stem)):
            raise ValueError("Arquivo compactado contém nome de dispositivo reservado.")
    root_path = Path(root).resolve()
    target = root_path.joinpath(*parts).resolve(strict=False)
    try:
        common = os.path.commonpath((str(root_path), str(target)))
        if os.path.normcase(common) != os.path.normcase(str(root_path)):
            raise ValueError("Arquivo compactado contém caminho inseguro.")
    except ValueError as exc:
        raise ValueError("Arquivo compactado contém caminho inseguro.") from exc
    return target

_INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')


def safe_filename_part(value: str, max_bytes: int = 200) -> str:
    text = _INVALID_FILENAME_CHARS.sub("_", value).strip().strip(".")
    text = re.sub(r"\s+", " ", text)
    if not text:
        text = "arquivo"
    # Keep Windows-compatible without assuming it is Windows.
    if text.upper() in {"CON", "PRN", "AUX", "NUL"} or re.fullmatch(r"COM[1-9]", text.upper()) or re.fullmatch(r"LPT[1-9]", text.upper()):
        text = "_" + text
    encoded = text.encode("utf-8", errors="ignore")
    if len(encoded) <= max_bytes:
        return text
    clipped = encoded[:max_bytes]
    while True:
        try:
            return clipped.decode("utf-8").rstrip(" .") or "arquivo"
        except UnicodeDecodeError:
            clipped = clipped[:-1]


def validate_download_dir(value: str) -> Path:
    path = Path(value).expanduser()
    if not value.strip():
        raise ValueError("Diretório vazio.")
    return path

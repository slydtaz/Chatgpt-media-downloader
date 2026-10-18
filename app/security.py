from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlsplit


SENSITIVE_QUERY_KEYS = re.compile(
    r"(?i)(?:token|access_token|auth|authorization|password|passwd|secret|sig|signature|"
    r"credential|cookie|session|apikey|api_key|key)=([^&#\s]+)"
)


def validate_url(url: str) -> tuple[bool, str]:
    value = url.strip()
    if not value:
        return False, "URL vazia."
    try:
        parsed = urlsplit(value)
    except ValueError:
        return False, "URL inválida."
    if parsed.scheme.lower() not in {"http", "https"}:
        return False, "Use uma URL HTTP ou HTTPS."
    if not parsed.netloc:
        return False, "URL inválida: domínio ausente."
    return True, ""


def redacted_url(url: str) -> str:
    value = url.strip()
    try:
        parsed = urlsplit(value)
        host = parsed.netloc
        if not host:
            return "<URL>"
        return f"{parsed.scheme}://{host}/<url-omitida>"
    except ValueError:
        return "<URL inválida>"


def redact_sensitive(text: str) -> str:
    if not text:
        return ""
    value = SENSITIVE_QUERY_KEYS.sub(lambda m: m.group(0).split("=")[0] + "=<redigido>", text)
    # Avoid persisting full URLs that may include signed query strings.
    value = re.sub(r"https?://[^\s]+", lambda m: redacted_url(m.group(0)), value)
    value = re.sub(r"(?i)(cookie|authorization|proxy-password|password)\s*[:=]\s*\S+", r"\1=<redigido>", value)
    return value


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

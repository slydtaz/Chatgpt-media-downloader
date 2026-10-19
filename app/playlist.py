from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .process_utils import hidden_subprocess_kwargs
from .security import redact_sensitive, validate_url
from .media_preview import choose_thumbnail_url


MAX_PLAYLIST_ENTRIES = 5_000


@dataclass(frozen=True)
class PlaylistEntry:
    index: int
    title: str
    url: str
    video_id: str = ""
    duration: float | None = None
    available: bool = True
    note: str = ""
    thumbnail_url: str = ""


@dataclass(frozen=True)
class PlaylistInfo:
    title: str
    entries: tuple[PlaylistEntry, ...]
    unavailable_count: int = 0
    extractor: str = ""

    @property
    def count(self) -> int:
        return len(self.entries)

    @property
    def available_count(self) -> int:
        return sum(1 for entry in self.entries if entry.available and entry.url)


def _absolute_entry_url(entry: dict[str, Any], parent_url: str) -> str:
    candidates = (entry.get("webpage_url"), entry.get("original_url"), entry.get("url"))
    for candidate in candidates:
        if not isinstance(candidate, str) or not candidate.strip():
            continue
        candidate = candidate.strip()
        if candidate.startswith("//"):
            candidate = "https:" + candidate
        ok, _ = validate_url(candidate)
        if ok:
            return candidate

    # Flat YouTube entries commonly return only the video id in `url`.
    parent = urlsplit(parent_url)
    host = (parent.hostname or "").lower()
    video_id = entry.get("id")
    extractor = str(entry.get("ie_key") or entry.get("extractor_key") or entry.get("extractor") or "").lower()
    if isinstance(video_id, str) and video_id and (
        host.endswith("youtube.com") or host.endswith("youtube-nocookie.com") or host.endswith("youtu.be")
    ) and ("youtube" in extractor or len(video_id) == 11):
        return f"https://www.youtube.com/watch?v={video_id}"
    return ""


def inspect_playlist(yt_dlp_path: Path | str, url: str, *, timeout: int = 180) -> PlaylistInfo:
    """Fetch flat playlist metadata without downloading media or bypassing access controls."""
    valid, message = validate_url(url)
    if not valid:
        raise ValueError(message)
    command = [
        str(yt_dlp_path), "--ignore-config", "--flat-playlist", "--dump-single-json", "--skip-download",
        "--yes-playlist", "--playlist-end", str(MAX_PLAYLIST_ENTRIES + 1),
        "--ignore-errors", "--no-warnings", "--no-progress", url,
    ]
    completed = subprocess.run(
        command, capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=timeout, check=False, **hidden_subprocess_kwargs(),
    )
    stdout = (completed.stdout or "").strip()
    payload: dict[str, Any] | None = None
    if stdout:
        try:
            parsed = json.loads(stdout)
            if isinstance(parsed, dict):
                payload = parsed
        except json.JSONDecodeError:
            # Be tolerant of non-JSON diagnostic lines, but only accept a full JSON object.
            for line in reversed(stdout.splitlines()):
                line = line.strip()
                if not line.startswith("{"):
                    continue
                try:
                    parsed = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(parsed, dict) and "entries" in parsed:
                    payload = parsed
                    break
    if payload is None:
        detail = redact_sensitive((completed.stderr or stdout).strip())
        if completed.returncode != 0:
            raise RuntimeError(detail[-2500:] or f"yt-dlp falhou ao analisar a playlist (código {completed.returncode}).")
        raise RuntimeError("O yt-dlp não retornou os metadados da playlist em formato válido.")

    raw_entries = payload.get("entries")
    if not isinstance(raw_entries, list):
        # For a video URL, make analysis fail clearly instead of treating it as a one-item playlist.
        raise RuntimeError("Esta URL não retornou uma lista de itens. Verifique se é uma playlist válida.")
    if len(raw_entries) > MAX_PLAYLIST_ENTRIES:
        raise RuntimeError(
            f"A playlist excede o limite seguro de {MAX_PLAYLIST_ENTRIES:,} itens por análise. "
            "Divida a lista em partes menores e tente novamente."
        )

    title = str(payload.get("title") or payload.get("playlist_title") or "Playlist sem título").strip()
    extractor = str(payload.get("extractor_key") or payload.get("extractor") or "")
    entries: list[PlaylistEntry] = []
    unavailable = 0
    for ordinal, item in enumerate(raw_entries, start=1):
        if not isinstance(item, dict):
            unavailable += 1
            entries.append(PlaylistEntry(ordinal, f"Item {ordinal} indisponível", "", available=False, note="O site não forneceu os dados deste item."))
            continue
        index = item.get("playlist_index")
        try:
            index = int(index) if index is not None else ordinal
        except (ValueError, TypeError):
            index = ordinal
        entry_url = _absolute_entry_url(item, url)
        thumbnail_url = choose_thumbnail_url(item, entry_url or url)
        availability = str(item.get("availability") or "").strip().lower()
        is_available = bool(entry_url) and availability not in {"private", "needs_auth", "premium_only"}
        note = "" if is_available else "URL não disponível nos metadados; não será baixado."
        if not is_available:
            unavailable += 1
        duration_raw = item.get("duration")
        try:
            duration = float(duration_raw) if duration_raw is not None else None
        except (ValueError, TypeError):
            duration = None
        entries.append(PlaylistEntry(
            index=index,
            title=str(item.get("title") or item.get("id") or f"Item {ordinal}").strip(),
            url=entry_url,
            video_id=str(item.get("id") or ""),
            duration=duration,
            available=is_available,
            note=note,
            thumbnail_url=thumbnail_url,
        ))
    return PlaylistInfo(title=title, entries=tuple(entries), unavailable_count=unavailable, extractor=extractor)


def format_duration(seconds: float | None) -> str:
    if seconds is None or seconds < 0:
        return "—"
    total = int(seconds)
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"

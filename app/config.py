from __future__ import annotations

import json
import os
import re
import platform as _platform
import tempfile
import uuid
import sys
from pathlib import Path
from typing import Any

APP_NAME = "ChatGPT Media Downloader"
PRODUCT_ID = "com.chatgpt.mediadownloader"
VENDOR = "ChatGPT"
VERSION = "5.3.2"


def _windows_local_appdata() -> Path:
    return Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))


def app_data_dir() -> Path:
    if os.name == "nt":
        return _windows_local_appdata() / "ChatGPT" / "MediaDownloader"
    if os.uname().sysname == "Darwin":
        return Path.home() / "Library" / "Application Support" / "ChatGPT" / "MediaDownloader"
    return Path(os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share")) / "ChatGPT" / "MediaDownloader"


APP_DATA = app_data_dir()
# In a PyInstaller one-file build, __file__ points inside the temporary extraction
# directory. The installed executable lives at sys.executable; never write persistent
# dependencies into PyInstaller's temporary _MEIPASS folder.
IS_FROZEN = bool(getattr(sys, "frozen", False))
INSTALL_ROOT = Path(sys.executable).resolve().parent if IS_FROZEN else Path(__file__).resolve().parents[1]
TOOLS_DIR = (APP_DATA / "tools") if IS_FROZEN else (INSTALL_ROOT / "tools")
TEMP_DIR = APP_DATA / "temp"
LOG_DIR = APP_DATA / "logs"
CONFIG_PATH = APP_DATA / "config" / "config.json"
BASELINE_CONFIG_PATH = APP_DATA / "config" / "installation_baseline.json"
INSTALL_ID_PATH = APP_DATA / "install_id.txt"
STARTUP_REPAIR_PENDING_PATH = TEMP_DIR / "startup-repair-pending.json"


def ensure_dirs() -> None:
    for directory in (APP_DATA, TOOLS_DIR, TEMP_DIR, LOG_DIR, CONFIG_PATH.parent):
        directory.mkdir(parents=True, exist_ok=True)


def startup_repair_is_pending() -> bool:
    """Return whether a previous startup repair still needs GUI confirmation."""
    try:
        return STARTUP_REPAIR_PENDING_PATH.exists()
    except OSError:
        # If the state cannot be inspected, fail closed to prevent a repair loop.
        return True


def mark_startup_repair_pending(version: str) -> None:
    """Persist a repair hand-off marker until the new GUI confirms startup."""
    payload = json.dumps({"version": str(version)[:32]}, ensure_ascii=False, indent=2)
    _write_atomic(STARTUP_REPAIR_PENDING_PATH, payload + "\n")


def clear_startup_repair_pending() -> bool:
    """Clear the hand-off marker after the GUI has successfully constructed."""
    try:
        STARTUP_REPAIR_PENDING_PATH.unlink(missing_ok=True)
        return True
    except OSError:
        return False


def _write_atomic(path: Path, data: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent), text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    finally:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass


def ensure_install_id() -> str:
    ensure_dirs()
    if INSTALL_ID_PATH.exists():
        value = INSTALL_ID_PATH.read_text(encoding="utf-8", errors="replace").strip()
        try:
            return str(uuid.UUID(value)).upper()
        except ValueError:
            pass
    value = str(uuid.uuid4()).upper()
    _write_atomic(INSTALL_ID_PATH, value + "\n")
    return value


def _platform_default_dirs() -> tuple[Path, Path]:
    system = _platform.system()
    if system == "Windows":
        base = Path.home() / "OneDrive" / "Desktop" / "musicas" / "Baixadas"
        return base / "Musicas", base / "Videos"
    if system == "Darwin":
        return Path.home() / "Music" / "ChatGPT Media Downloader", Path.home() / "Movies" / "ChatGPT Media Downloader"
    return Path.home() / "Music" / "ChatGPT Media Downloader", Path.home() / "Videos" / "ChatGPT Media Downloader"


DEFAULT_MUSIC_DIR, DEFAULT_VIDEO_DIR = _platform_default_dirs()

DEFAULT_CONFIG: dict[str, Any] = {
    "music_dir": str(DEFAULT_MUSIC_DIR),
    "video_dir": str(DEFAULT_VIDEO_DIR),
    "auto_video_quality": 1080,
    "audio_bitrate": 192,
    "yt_dlp_path": "",
    "ffmpeg_path": "",
    "ffprobe_path": "",
    "theme": "dark",
    "accent_color": "#8B5CF6",
    "ui_density": "comfortable",
    "developer_mode": False,
    "animations_enabled": False,
    "playlist_strategy": "sequential",
    "playlist_parallelism": 3,
    "concurrent_fragments": 4,
    "retries": 5,
    "video_container": "mp4",
    "subtitle_mode": "off",
    "update_open_after": True,
    "update_check_on_startup": True,
    "settings_schema_version": 3,
}


def _looks_foreign_path(value: str) -> bool:
    if not value:
        return False
    # A Windows drive path should not silently become a Linux/macOS relative path.
    return os.name != "nt" and len(value) >= 3 and value[1] == ":" and value[2] in {"\\", "/"}


def load_config() -> dict[str, Any]:
    ensure_dirs()
    data = dict(DEFAULT_CONFIG)
    loaded_config: dict[str, Any] = {}
    if CONFIG_PATH.exists():
        try:
            loaded = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                loaded_config = loaded
                data.update(loaded)
        except (OSError, json.JSONDecodeError):
            pass

    # One-time visual migration: replace only the previous built-in blue accent.
    # Explicitly customized colors and other saved preferences remain intact.
    try:
        schema_version = int(loaded_config.get("settings_schema_version", 1))
    except (TypeError, ValueError):
        schema_version = 1
    if schema_version < 3:
        legacy_accent = str(
            loaded_config.get("accent_color", DEFAULT_CONFIG["accent_color"]) or DEFAULT_CONFIG["accent_color"]
        ).strip().upper()
        if legacy_accent in {"", "#2563EB"}:
            data["accent_color"] = DEFAULT_CONFIG["accent_color"]
        data["settings_schema_version"] = 3

    for key in ("music_dir", "video_dir", "yt_dlp_path", "ffmpeg_path", "ffprobe_path"):
        data[key] = str(data.get(key) or "")

    if _looks_foreign_path(data["music_dir"]):
        data["music_dir"] = DEFAULT_CONFIG["music_dir"]
    if _looks_foreign_path(data["video_dir"]):
        data["video_dir"] = DEFAULT_CONFIG["video_dir"]

    try:
        data["auto_video_quality"] = int(data.get("auto_video_quality", 1080))
    except (ValueError, TypeError):
        data["auto_video_quality"] = 1080
    try:
        data["audio_bitrate"] = int(data.get("audio_bitrate", 192))
    except (ValueError, TypeError):
        data["audio_bitrate"] = 192
    if data["auto_video_quality"] not in {480, 720, 1080, 1440, 2160}:
        data["auto_video_quality"] = 1080
    if data["audio_bitrate"] not in {128, 192, 320}:
        data["audio_bitrate"] = 192
    if data.get("theme") not in {"system", "dark", "light", "oled"}:
        data["theme"] = "dark"
    accent = str(data.get("accent_color", DEFAULT_CONFIG["accent_color"]) or DEFAULT_CONFIG["accent_color"]).strip()
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", accent):
        accent = DEFAULT_CONFIG["accent_color"]
    data["accent_color"] = accent.upper()
    if data.get("ui_density") not in {"comfortable", "compact"}:
        data["ui_density"] = "comfortable"
    if data.get("playlist_strategy") not in {"sequential", "parallel"}:
        data["playlist_strategy"] = "sequential"
    try:
        data["playlist_parallelism"] = int(data.get("playlist_parallelism", 3))
    except (ValueError, TypeError):
        data["playlist_parallelism"] = 3
    if data["playlist_parallelism"] not in {2, 3, 4, 6}:
        data["playlist_parallelism"] = 3
    try:
        data["concurrent_fragments"] = int(data.get("concurrent_fragments", 4))
    except (ValueError, TypeError):
        data["concurrent_fragments"] = 4
    if data["concurrent_fragments"] not in {1, 2, 4, 8, 16}:
        data["concurrent_fragments"] = 4
    try:
        data["retries"] = int(data.get("retries", 5))
    except (ValueError, TypeError):
        data["retries"] = 5
    if data["retries"] not in {2, 3, 5, 10}:
        data["retries"] = 5
    if data.get("video_container") not in {"mp4", "mkv"}:
        data["video_container"] = "mp4"
    if data.get("subtitle_mode") not in {"off", "manual", "all"}:
        data["subtitle_mode"] = "off"
    for option in ("update_open_after", "update_check_on_startup"):
        value = data.get(option, True)
        if isinstance(value, bool):
            data[option] = value
        elif isinstance(value, (int, float)):
            data[option] = bool(value)
        else:
            data[option] = str(value).strip().lower() in {"1", "true", "yes", "sim", "on"}
    data["settings_schema_version"] = 3
    return data


def save_config(config: dict[str, Any]) -> None:
    ensure_dirs()
    clean = dict(DEFAULT_CONFIG)
    clean.update(config)
    payload = json.dumps(clean, ensure_ascii=False, indent=2)
    _write_atomic(CONFIG_PATH, payload + "\n")


def save_installation_baseline(config: dict[str, Any] | None = None, *, overwrite: bool = False) -> None:
    ensure_dirs()
    if BASELINE_CONFIG_PATH.exists() and not overwrite:
        return
    snapshot = dict(config or load_config())
    _write_atomic(BASELINE_CONFIG_PATH, json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n")


def load_installation_baseline() -> dict[str, Any]:
    if BASELINE_CONFIG_PATH.exists():
        try:
            loaded = json.loads(BASELINE_CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                result = dict(DEFAULT_CONFIG)
                result.update(loaded)
                return result
        except (OSError, json.JSONDecodeError):
            pass
    return load_config()

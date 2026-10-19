from __future__ import annotations

import json
import re
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from .dependencies import ToolInfo, inspect_tool
from .security import redact_sensitive, safe_filename_part, validate_url
from .process_utils import hidden_subprocess_kwargs, refresh_windows_shell_items


ProgressCallback = Callable[[dict], None]
LogCallback = Callable[[str], None]


@dataclass
class DownloadResult:
    returncode: int
    message: str
    details: str
    output_dir: Path
    completed_with_warnings: bool = False


_PROGRESS = re.compile(
    r"\[download\]\s+(?P<pct>\d+(?:\.\d+)?)%\s+of\s+(?P<total>[^\s]+)\s+at\s+(?P<speed>[^\s]+)\s+ETA\s+(?P<eta>[^\s]+)"
)
_PROGRESS_SHORT = re.compile(
    r"\[download\]\s+(?P<pct>\d+(?:\.\d+)?)%"
)
_MEDIA_EXTENSIONS = {".mp3", ".m4a", ".aac", ".flac", ".opus", ".wav", ".mp4", ".mkv", ".webm", ".mov", ".avi"}


def playlist_finished_with_warnings(returncode: int, details: str) -> bool:
    """Recognize yt-dlp's completed-playlist marker even if one item was unavailable.

    yt-dlp can return exit code 1 for a playlist with unavailable entries even
    after it reaches its final 'Finished downloading playlist' marker. Keep the
    original code for diagnostics, but let the GUI report this as a partial
    completion instead of incorrectly claiming every file failed.
    """
    return returncode != 0 and "[download] Finished downloading playlist:" in details


def _refresh_recent_media_in_explorer(output_dir: Path, started_at: float, logger) -> int:
    """Ask Windows Explorer to refresh thumbnails for media written by this run.

    This is a refresh notification only; whether Explorer renders embedded
    MP3 artwork still depends on the Windows thumbnail handler and view settings.
    """
    if not output_dir.exists():
        return 0
    recent: list[Path] = []
    try:
        for item in output_dir.rglob("*"):
            try:
                if item.is_file() and item.suffix.lower() in _MEDIA_EXTENSIONS and item.stat().st_mtime >= started_at - 5:
                    recent.append(item)
            except OSError:
                continue
    except OSError:
        return 0
    try:
        count = refresh_windows_shell_items(recent)
        if count:
            logger.info("Solicitada atualização das miniaturas do Explorador para %d arquivo(s).", count)
        return count
    except Exception:
        logger.debug("Não foi possível solicitar atualização das miniaturas ao shell.", exc_info=True)
        return 0


def choose_video_height(requested: int, formats: list[dict]) -> tuple[int, bool]:
    heights = sorted(
        {
            int(f["height"])
            for f in formats
            if f.get("height") and isinstance(f.get("height"), (int, float)) and int(f["height"]) > 0
        }
    )
    if not heights:
        return requested, False
    eligible = [h for h in heights if h <= requested]
    if eligible:
        selected = max(eligible)
    else:
        selected = min(heights)
    return selected, selected != requested


def _format_progress(line: str) -> Optional[dict]:
    match = _PROGRESS.search(line)
    if not match:
        match = _PROGRESS_SHORT.search(line)
        if not match:
            return None
        return {"percent": float(match.group("pct")), "stage": "Baixando", "raw": redact_sensitive(line)}
    return {
        "percent": min(100.0, float(match.group("pct"))),
        "total": match.group("total"),
        "speed": match.group("speed"),
        "eta": match.group("eta"),
        "stage": "Baixando",
        "raw": redact_sensitive(line),
    }


def build_video_command(
    yt_dlp_path: Path | str,
    ffmpeg_path: Path | str,
    output_template: Path | str,
    selected_height: int,
    url: str,
    playlist: bool = False,
    *,
    container: str = "mp4",
    retries: int = 5,
    fragment_retries: int = 5,
    concurrent_fragments: int = 4,
    subtitle_mode: str = "off",
) -> list[str]:
    """Build argument-list-only yt-dlp invocation with thumbnail and metadata embedding."""
    if container not in {"mp4", "mkv"}:
        container = "mp4"
    retries = retries if retries in {2, 3, 5, 10} else 5
    fragment_retries = retries
    concurrent_fragments = concurrent_fragments if concurrent_fragments in {1, 2, 4, 8, 16} else 4
    command = [
        str(yt_dlp_path), "--ignore-config", "--newline", "--yes-playlist" if playlist else "--no-playlist",
        "--check-formats", "-f",
        f"bv*[height<={selected_height}]+ba/b[height<={selected_height}]/bv*+ba/b",
        "--merge-output-format", container, "--remux-video", container,
        "--embed-thumbnail", "--embed-metadata", "--retries", str(retries),
        "--fragment-retries", str(fragment_retries), "--concurrent-fragments", str(concurrent_fragments),
        "--ffmpeg-location", str(ffmpeg_path), "-o", str(output_template),
    ]
    if subtitle_mode in {"manual", "all"}:
        command.append("--write-subs")
    if subtitle_mode == "all":
        command.extend(["--write-auto-subs", "--sub-langs", "all"])
    command.append(url)
    return command


class Downloader:
    def __init__(
        self,
        yt_dlp: ToolInfo,
        ffmpeg: ToolInfo,
        ffprobe: ToolInfo,
        logger,
        progress: Optional[ProgressCallback] = None,
        output: Optional[LogCallback] = None,
        options: dict | None = None,
    ):
        self.yt_dlp = yt_dlp
        self.ffmpeg = ffmpeg
        self.ffprobe = ffprobe
        self.logger = logger
        self.download_logger = logger.getChild("download")
        self.progress = progress or (lambda data: None)
        self.output = output or (lambda text: None)
        self.options = dict(options or {})
        self.process: Optional[subprocess.Popen[str]] = None
        self._cancel = threading.Event()
        self._lock = threading.Lock()

    def cancel(self) -> None:
        self._cancel.set()
        with self._lock:
            process = self.process
        if process and process.poll() is None:
            try:
                process.terminate()
            except OSError:
                pass

    def _check_common(self, url: str) -> None:
        valid, message = validate_url(url)
        if not valid:
            raise ValueError(message)
        if not self.yt_dlp.path or not self.yt_dlp.executable_ok:
            raise RuntimeError("yt-dlp não foi encontrado ou não pôde ser executado.")
        if not self.ffmpeg.path or not self.ffmpeg.executable_ok:
            raise RuntimeError("FFmpeg não foi encontrado ou não pôde ser executado.")

    def _probe_formats(self, url: str) -> list[dict]:
        command = [
            str(self.yt_dlp.path),
            "--ignore-config",
            "--no-playlist",
            "--skip-download",
            "--dump-single-json",
            "--no-warnings",
            url,
        ]
        self.download_logger.info("Consultando formatos para %s", redact_sensitive(url))
        if self._cancel.is_set():
            return []
        process = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            encoding="utf-8", errors="replace", **hidden_subprocess_kwargs(),
        )
        with self._lock:
            if self._cancel.is_set():
                try:
                    process.terminate()
                except OSError:
                    pass
            self.process = process
        try:
            stdout, stderr = process.communicate(timeout=90)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate()
            raise RuntimeError("A consulta de formatos excedeu o limite de 90 segundos.")
        finally:
            with self._lock:
                if self.process is process:
                    self.process = None
        if self._cancel.is_set():
            return []
        if process.returncode != 0:
            details = redact_sensitive((stderr or stdout).strip())
            raise RuntimeError(details or f"yt-dlp retornou {process.returncode} ao consultar formatos.")
        try:
            data = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError("yt-dlp não retornou dados de formatos válidos.") from exc
        return data.get("formats", [])

    def _run(self, command: list[str]) -> DownloadResult:
        self.download_logger.info("Iniciando execução do yt-dlp; URL e caminhos locais não são gravados.")
        if self._cancel.is_set():
            return DownloadResult(130, "Download cancelado.", "", Path("."))
        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                **hidden_subprocess_kwargs(),
            )
            with self._lock:
                self.process = process
                if self._cancel.is_set():
                    try:
                        process.terminate()
                    except OSError:
                        pass
        except OSError as exc:
            self.logger.exception("Falha ao iniciar yt-dlp.")
            return DownloadResult(1, f"Não foi possível iniciar o yt-dlp: {exc}", str(exc), Path("."))

        details: list[str] = []
        assert process.stdout is not None
        for raw in process.stdout:
            line = raw.rstrip()
            if self._cancel.is_set():
                break
            if line:
                details.append(redact_sensitive(line))
                self.output(redact_sensitive(line))
                parsed = _format_progress(line)
                if parsed:
                    self.progress(parsed)
                elif line.startswith("["):
                    self.progress({"stage": line.split("]", 1)[0].lstrip("[")[:40], "percent": None, "raw": redact_sensitive(line)})
        if self._cancel.is_set() and process.poll() is None:
            try:
                process.terminate()
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
            except OSError:
                pass
        rc = process.wait()
        with self._lock:
            if self.process is process:
                self.process = None
        detail_text = "\n".join(details[-120:])
        if self._cancel.is_set():
            return DownloadResult(130, "Download cancelado.", detail_text, Path("."))
        if rc == 0:
            return DownloadResult(0, "Download concluído.", detail_text, Path("."))
        if playlist_finished_with_warnings(rc, detail_text):
            message = (
                f"A playlist terminou de ser processada, mas o yt-dlp retornou código {rc}. "
                "Um ou mais itens podem estar indisponíveis ou ter gerado avisos. "
                "Os arquivos já concluídos foram preservados; confira os detalhes abaixo."
            )
            return DownloadResult(rc, message, detail_text, Path("."), completed_with_warnings=True)
        return DownloadResult(rc, f"O yt-dlp terminou com código {rc}.", detail_text, Path("."))

    def download_video(self, url: str, quality: int, output_dir: Path, playlist: bool = False) -> DownloadResult:
        self._check_common(url)
        output_dir.mkdir(parents=True, exist_ok=True)
        if self._cancel.is_set():
            return DownloadResult(130, "Download cancelado.", "", output_dir)
        formats = self._probe_formats(url)
        if self._cancel.is_set():
            return DownloadResult(130, "Download cancelado durante a consulta de formatos.", "", output_dir)
        selected, fallback = choose_video_height(quality, formats)

        if fallback and selected < quality:
            message = f"{quality}p não estava disponível. Foi selecionado {selected}p."
            self.output(message)
            self.logger.info(message)
        elif fallback:
            message = f"{quality}p não estava disponível; foi usado o formato compatível disponível de {selected}p."
            self.output(message)
            self.logger.info(message)

        output_template = str(output_dir / ("%(playlist_title).100B/%(playlist_index)03d - %(title).180B [%(id)s].%(ext)s" if playlist else "%(title).200B [%(id)s].%(ext)s"))
        command = build_video_command(
            self.yt_dlp.path,
            self.ffmpeg.path,
            output_template,
            selected,
            url,
            playlist=playlist,
            container=str(self.options.get("video_container", "mp4")),
            retries=int(self.options.get("retries", 5)),
            fragment_retries=int(self.options.get("retries", 5)),
            concurrent_fragments=int(self.options.get("concurrent_fragments", 4)),
            subtitle_mode=str(self.options.get("subtitle_mode", "off")),
        )
        started_at = time.time()
        result = self._run(command)
        _refresh_recent_media_in_explorer(output_dir, started_at, self.download_logger)
        result = DownloadResult(result.returncode, result.message, result.details, output_dir, result.completed_with_warnings)
        if result.returncode == 0:
            self.progress({"percent": 100.0, "stage": "Concluído"})
            if fallback:
                result.message = f"Concluído. {quality}p não estava disponível; selecionado {selected}p."
        return result

    def download_audio(self, url: str, bitrate: int, output_dir: Path, playlist: bool = False) -> DownloadResult:
        self._check_common(url)
        output_dir.mkdir(parents=True, exist_ok=True)
        output_template = str(output_dir / ("%(playlist_title).100B/%(playlist_index)03d - %(title).180B [%(id)s].%(ext)s" if playlist else "%(title).200B [%(id)s].%(ext)s"))
        command = [
            str(self.yt_dlp.path),
            "--ignore-config",
            "--newline",
            "--yes-playlist" if playlist else "--no-playlist",
            "--retries",
            str(int(self.options.get("retries", 5)) if int(self.options.get("retries", 5)) in {2, 3, 5, 10} else 5),
            "--fragment-retries",
            str(int(self.options.get("retries", 5)) if int(self.options.get("retries", 5)) in {2, 3, 5, 10} else 5),
            "--concurrent-fragments",
            str(int(self.options.get("concurrent_fragments", 4)) if int(self.options.get("concurrent_fragments", 4)) in {1, 2, 4, 8, 16} else 4),
            "-x",
            "--audio-format",
            "mp3",
            "--audio-quality",
            f"{bitrate}K",
            "--embed-metadata",
            "--embed-thumbnail",
            "--ffmpeg-location",
            str(self.ffmpeg.path),
            "-o",
            output_template,
            url,
        ]
        started_at = time.time()
        result = self._run(command)
        _refresh_recent_media_in_explorer(output_dir, started_at, self.download_logger)
        result = DownloadResult(result.returncode, result.message, result.details, output_dir, result.completed_with_warnings)
        if result.returncode == 0:
            self.progress({"percent": 100.0, "stage": "Concluído"})
        return result


def validate_quality(value: int) -> bool:
    return value in {480, 720, 1080, 1440, 2160}


def validate_bitrate(value: int) -> bool:
    return value in {128, 192, 320}

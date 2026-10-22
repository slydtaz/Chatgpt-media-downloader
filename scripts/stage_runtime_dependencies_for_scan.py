from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import VERSION
from app.platform import detect_system
from app.updater import install_tool_from_release


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().lower()


def main() -> int:
    system = detect_system()
    if system.os_name != "Windows" or system.architecture != "x64":
        raise RuntimeError(f"Release dependency scan expects Windows x64, got {system.os_label}.")

    target_dir = ROOT / "dist" / "security-scan-inputs"
    shutil.rmtree(target_dir, ignore_errors=True)
    target_dir.mkdir(parents=True, exist_ok=True)

    # These are the exact official upstream tools the app's own updater installs.
    # install_tool_from_release enforces trusted HTTPS redirects and upstream SHA-256.
    yt_dlp, yt_release = install_tool_from_release("yt-dlp", system)
    ffmpeg, ffmpeg_release = install_tool_from_release("ffmpeg", system)
    ffprobe = ffmpeg.with_name(f"ChatGPT.MediaDownloader.ffprobe{ffmpeg.suffix}")
    if not yt_dlp.is_file() or not ffmpeg.is_file() or not ffprobe.is_file():
        raise RuntimeError("The verified updater did not produce all three runtime binaries.")

    inputs = [("yt-dlp.exe", yt_dlp), ("ffmpeg.exe", ffmpeg), ("ffprobe.exe", ffprobe)]
    rows = [
        "Security inventory for ChatGPT Media Downloader beta",
        f"Application version: {VERSION}",
        f"Scan runner: {system.os_label}",
        "Retrieval: app.updater.install_tool_from_release",
        "Integrity: upstream asset size/redirect checks and SHA-256 checksum-manifest validation completed before staging.",
        "VirusTotal submissions are public-community submissions; this inventory contains only public upstream runtime tools.",
        f"yt-dlp upstream release tag: {yt_release}",
        f"FFmpeg upstream release tag: {ffmpeg_release}",
        "",
        "Staged sample inventory:",
    ]
    sample_meta = []
    for display_name, original in inputs:
        target = target_dir / display_name
        shutil.copy2(original, target)
        digest = sha256(target)
        sample_meta.append({"name": display_name, "sha256": digest, "bytes": target.stat().st_size})
        rows.append(
            f"{display_name}: SHA256={digest}; bytes={target.stat().st_size}; "
            f"staged_path=security-scan-inputs/{display_name}"
        )
        print(f"Staged {display_name}: {target.stat().st_size} bytes; SHA256={digest}")

    inventory = ROOT / "dist" / "Security-Inventory.txt"
    inventory.write_text("\n".join(rows) + "\n", encoding="utf-8")
    (target_dir / "dependency-versions.json").write_text(
        json.dumps(
            {
                "application_version": VERSION,
                "os": system.os_label,
                "yt_dlp_release": yt_release,
                "ffmpeg_release": ffmpeg_release,
                "samples": sample_meta,
            },
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {inventory}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

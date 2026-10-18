import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.playlist import PlaylistEntry, PlaylistInfo, format_duration, inspect_playlist
from app.downloader import build_video_command
from app import config


class PlaylistMetadataTests(unittest.TestCase):
    def test_youtube_flat_playlist_count_and_urls(self):
        payload = {
            "title": "Sample Mix",
            "extractor_key": "YoutubeTab",
            "entries": [
                {"id": "abcdefghijk", "title": "Song One", "ie_key": "Youtube", "playlist_index": 1, "duration": 121},
                {"id": "lmnopqrstuv", "title": "Song Two", "ie_key": "Youtube", "playlist_index": 2},
                None,
            ],
        }
        completed = subprocess.CompletedProcess(args=[], returncode=0, stdout=json.dumps(payload), stderr="")
        with patch("app.playlist.subprocess.run", return_value=completed) as run:
            info = inspect_playlist("yt-dlp", "https://www.youtube.com/playlist?list=PLsample")
        self.assertEqual(info.title, "Sample Mix")
        self.assertEqual(info.count, 3)
        self.assertEqual(info.available_count, 2)
        self.assertEqual(info.entries[0].url, "https://www.youtube.com/watch?v=abcdefghijk")
        self.assertFalse(info.entries[2].available)
        command = run.call_args.args[0]
        self.assertIn("--flat-playlist", command)
        self.assertIn("--dump-single-json", command)
        self.assertNotIn("--download-archive", command)

    def test_rejects_invalid_url_without_launching_process(self):
        with patch("app.playlist.subprocess.run") as run:
            with self.assertRaises(ValueError):
                inspect_playlist("yt-dlp", "file:///etc/passwd")
        run.assert_not_called()

    def test_missing_json_produces_clear_failure(self):
        completed = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="ERROR: playlist unavailable")
        with patch("app.playlist.subprocess.run", return_value=completed):
            with self.assertRaisesRegex(RuntimeError, "playlist unavailable"):
                inspect_playlist("yt-dlp", "https://example.com/playlist/1")

    def test_duration_format(self):
        self.assertEqual(format_duration(65), "1:05")
        self.assertEqual(format_duration(3661), "1:01:01")
        self.assertEqual(format_duration(None), "—")


class PlaylistOptionsTests(unittest.TestCase):
    def test_video_command_honors_container_retries_fragments_subtitles(self):
        command = build_video_command("yt-dlp", "ffmpeg", Path("out.mp4"), 1080, "https://example.com/video/1",
                                      container="mkv", retries=3, concurrent_fragments=8, subtitle_mode="all")
        self.assertIn("mkv", command)
        self.assertIn("3", command)
        self.assertIn("8", command)
        self.assertIn("--write-subs", command)
        self.assertIn("--write-auto-subs", command)
        self.assertIn("--sub-langs", command)

    def test_config_defaults_cap_parallelism(self):
        self.assertEqual(config.DEFAULT_CONFIG["playlist_strategy"], "sequential")
        self.assertEqual(config.DEFAULT_CONFIG["playlist_parallelism"], 3)
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            cfgpath = base / "config.json"
            cfgpath.write_text(json.dumps({"playlist_strategy": "parallel", "playlist_parallelism": 999,
                                           "concurrent_fragments": -4, "retries": 0}), encoding="utf-8")
            with patch.object(config, "APP_DATA", base), patch.object(config, "TOOLS_DIR", base / "tools"), \
                 patch.object(config, "TEMP_DIR", base / "temp"), patch.object(config, "LOG_DIR", base / "logs"), \
                 patch.object(config, "CONFIG_PATH", cfgpath):
                result = config.load_config()
        self.assertEqual(result["playlist_strategy"], "parallel")
        self.assertEqual(result["playlist_parallelism"], 3)
        self.assertEqual(result["concurrent_fragments"], 4)
        self.assertEqual(result["retries"], 5)


if __name__ == "__main__":
    unittest.main()

import unittest
import logging
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

from app.downloader import Downloader, DownloadResult, build_video_command, choose_video_height, playlist_finished_with_warnings, _refresh_recent_media_in_explorer
from app.dependencies import ToolInfo
from app.security import validate_url


class DownloaderTests(unittest.TestCase):
    def setUp(self):
        self.formats = [
            {"format_id": "18", "height": 360},
            {"format_id": "22", "height": 720},
            {"format_id": "137", "height": 1080},
        ]

    def test_fallback_to_lower_resolution(self):
        selected, fallback = choose_video_height(1440, self.formats)
        self.assertEqual(selected, 1080)
        self.assertTrue(fallback)

    def test_exact_quality(self):
        selected, fallback = choose_video_height(720, self.formats)
        self.assertEqual(selected, 720)
        self.assertFalse(fallback)

    def test_no_lower_quality_uses_smallest_available(self):
        selected, fallback = choose_video_height(
            480,
            [{"height": 720}, {"height": 1080}],
        )
        self.assertEqual(selected, 720)
        self.assertTrue(fallback)


    def test_audio_download_ignores_external_yt_dlp_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            yt = ToolInfo("yt-dlp", Path("yt-dlp"), executable_ok=True)
            ffmpeg = ToolInfo("ffmpeg", Path("ffmpeg"), executable_ok=True)
            ffprobe = ToolInfo("ffprobe", Path("ffprobe"), executable_ok=True)
            downloader = Downloader(yt, ffmpeg, ffprobe, logging.getLogger("test"))
            with patch.object(downloader, "_run", return_value=DownloadResult(0, "ok", "", root)) as run, \
                 patch("app.downloader._refresh_recent_media_in_explorer", return_value=0):
                downloader.download_audio("https://example.com/audio", 192, root)
            command = run.call_args.args[0]
            self.assertEqual(command[1], "--ignore-config")
            self.assertEqual(command[-1], "https://example.com/audio")

    def test_format_probe_ignores_external_yt_dlp_config(self):
        class FakeProcess:
            returncode = 0
            def communicate(self, timeout):
                return ('{"formats": []}', "")

        yt = ToolInfo("yt-dlp", Path("yt-dlp"), executable_ok=True)
        ffmpeg = ToolInfo("ffmpeg", Path("ffmpeg"), executable_ok=True)
        ffprobe = ToolInfo("ffprobe", Path("ffprobe"), executable_ok=True)
        downloader = Downloader(yt, ffmpeg, ffprobe, logging.getLogger("test"))
        fake_process = FakeProcess()
        with patch("app.downloader.subprocess.Popen", return_value=fake_process) as popen:
            self.assertEqual(downloader._probe_formats("https://example.com/video"), [])
        command = popen.call_args.args[0]
        self.assertEqual(command[1], "--ignore-config")

    def test_video_command_embeds_thumbnail_without_leaving_sidecar(self):
        command = build_video_command("yt-dlp.exe", "ffmpeg.exe", "C:/Videos/%(title)s.%(ext)s", 1080, "https://example.com/watch/123")
        self.assertIn("--ignore-config", command)
        self.assertIn("--embed-thumbnail", command)
        self.assertIn("--embed-metadata", command)
        self.assertIn("--remux-video", command)
        self.assertIn("mp4", command)
        self.assertNotIn("--write-thumbnail", command)
        self.assertEqual(command[-1], "https://example.com/watch/123")

    def test_playlist_video_command_enables_all_entries(self):
        command = build_video_command("yt-dlp", "ffmpeg", "/videos/%(playlist_index)s - %(title)s.%(ext)s", 1080, "https://www.youtube.com/playlist?list=PL123", playlist=True)
        self.assertIn("--ignore-config", command)
        self.assertIn("--yes-playlist", command)
        self.assertNotIn("--no-playlist", command)
        self.assertEqual(command[-1], "https://www.youtube.com/playlist?list=PL123")


    def test_finished_playlist_with_nonzero_code_is_partial_success_warning(self):
        details = "WARNING: one unavailable video is hidden\n[download] Finished downloading playlist: Example"
        self.assertTrue(playlist_finished_with_warnings(1, details))

    def test_non_playlist_error_is_not_relabelled_as_completed_playlist(self):
        self.assertFalse(playlist_finished_with_warnings(1, "ERROR: network failure"))

    def test_zero_exit_is_not_labelled_as_warning(self):
        self.assertFalse(playlist_finished_with_warnings(0, "[download] Finished downloading playlist: Example"))


    def test_refreshes_recent_media_files_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fresh = root / "new.mp3"
            fresh.write_bytes(b"test")
            old = root / "old.mp3"
            old.write_bytes(b"test")
            old_time = time.time() - 600
            import os
            os.utime(old, (old_time, old_time))
            unrelated = root / "cover.jpg"
            unrelated.write_bytes(b"test")
            with patch("app.downloader.refresh_windows_shell_items", return_value=1) as refresh:
                count = _refresh_recent_media_in_explorer(root, time.time() - 10, logging.getLogger("test"))
            self.assertEqual(count, 1)
            notified = refresh.call_args.args[0]
            self.assertIn(fresh, notified)
            self.assertNotIn(old, notified)
            self.assertNotIn(unrelated, notified)

    def test_http_https_only(self):
        self.assertTrue(validate_url("http://example.com")[0])
        self.assertTrue(validate_url("https://example.com")[0])
        self.assertFalse(validate_url("file:///C:/test")[0])


if __name__ == "__main__":
    unittest.main()

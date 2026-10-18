import logging
import os
import queue
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from app.downloader import DownloadResult
from app.gui import MediaDownloaderApp


class FakeDownloader:
    tracker = {"lock": threading.Lock(), "active": 0, "max_active": 0, "calls": []}

    def __init__(self, yt, ffmpeg, ffprobe, logger, progress=None, output=None, options=None):
        self.progress = progress or (lambda data: None)
        self.output = output or (lambda line: None)
        self.options = dict(options or {})

    def _run_item(self, mode, url, value, output_dir):
        tracker = self.tracker
        with tracker["lock"]:
            tracker["active"] += 1
            tracker["max_active"] = max(tracker["max_active"], tracker["active"])
            tracker["calls"].append((mode, url, value, Path(output_dir), dict(self.options)))
        try:
            self.progress({"percent": 50, "stage": "Baixando"})
            self.output(f"simulated {mode}")
            time.sleep(0.04)
            self.progress({"percent": 100, "stage": "Concluído"})
            return DownloadResult(0, "Download concluído.", "", Path(output_dir))
        finally:
            with tracker["lock"]:
                tracker["active"] -= 1

    def download_audio(self, url, bitrate, output_dir, playlist=False):
        return self._run_item("music", url, bitrate, output_dir)

    def download_video(self, url, quality, output_dir, playlist=False):
        return self._run_item("video", url, quality, output_dir)


class PlaylistExecutionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.app = MediaDownloaderApp.__new__(MediaDownloaderApp)
        self.app.cancel_requested = threading.Event()
        self.app.active_downloaders = {}
        self.app.active_downloaders_lock = threading.Lock()
        self.app.ui_queue = queue.Queue()
        self.app.logger = logging.getLogger("playlist-test")
        with FakeDownloader.tracker["lock"]:
            FakeDownloader.tracker.update(active=0, max_active=0, calls=[])
        self.config = {
            "music_dir": str(self.root / "Music"),
            "video_dir": str(self.root / "Videos"),
            "video_container": "mkv",
            "retries": 3,
            "concurrent_fragments": 8,
            "subtitle_mode": "all",
        }
        self.dependencies = {"yt-dlp": object(), "ffmpeg": object(), "ffprobe": object()}
        self.items = [
            {"position": 0, "index": 1, "title": "Clip A", "url": "https://example.com/video/a", "available": True, "mode": "video", "value": 1080},
            {"position": 1, "index": 2, "title": "Track B", "url": "https://example.com/video/b", "available": True, "mode": "music", "value": 320},
            {"position": 2, "index": 3, "title": "Clip C", "url": "https://example.com/video/c", "available": True, "mode": "video", "value": 720},
            {"position": 3, "index": 4, "title": "Track D", "url": "https://example.com/video/d", "available": True, "mode": "music", "value": 128},
        ]

    def tearDown(self):
        self.temp.cleanup()

    def _execute(self, strategy, workers=3):
        with patch("app.gui.Downloader", FakeDownloader):
            MediaDownloaderApp._playlist_download_worker(
                self.app, self.items, strategy, workers, "Test / Playlist", self.config, self.dependencies
            )
        events = []
        while not self.app.ui_queue.empty():
            events.append(self.app.ui_queue.get_nowait())
        return events

    def test_mixed_per_item_types_and_qualities_are_sent_to_downloader(self):
        events = self._execute("sequential")
        calls = FakeDownloader.tracker["calls"]
        self.assertEqual(len(calls), 4)
        self.assertEqual([(call[0], call[2]) for call in calls], [("video", 1080), ("music", 320), ("video", 720), ("music", 128)])
        self.assertTrue(all(call[4]["video_container"] == "mkv" and call[4]["retries"] == 3 for call in calls))
        for mode, _url, _value, output_path, _options in calls:
            expected_base = self.root / ("Music" if mode == "music" else "Videos") / "Test _ Playlist"
            self.assertEqual(output_path, expected_base)
        summary = [data for kind, data in events if kind == "playlist_download_done"][-1]
        self.assertEqual(summary["success"], 4)
        self.assertEqual(summary["failed"], 0)

    def test_sequential_mode_uses_one_worker(self):
        self._execute("sequential")
        self.assertEqual(FakeDownloader.tracker["max_active"], 1)

    @unittest.skipIf(
        os.name == "nt" and os.environ.get("GITHUB_ACTIONS") == "true",
        "GitHub-hosted Windows runner interrupts worker-thread startup with KeyboardInterrupt; "
        "parallel mode remains tested on POSIX CI and local Windows runs.",
    )
    def test_parallel_mode_is_bounded_by_requested_worker_count(self):
        self._execute("parallel", workers=3)
        self.assertGreater(FakeDownloader.tracker["max_active"], 1)
        self.assertLessEqual(FakeDownloader.tracker["max_active"], 3)


if __name__ == "__main__":
    unittest.main()

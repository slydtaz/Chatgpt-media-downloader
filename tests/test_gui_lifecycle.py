from __future__ import annotations

import threading
import unittest

from app.gui import MediaDownloaderApp


class FakeRoot:
    def __init__(self):
        self.cancelled = []
        self.destroyed = False

    def after_cancel(self, identifier):
        self.cancelled.append(identifier)

    def destroy(self):
        self.destroyed = True


class FakeExecutor:
    def __init__(self):
        self.shutdown_args = None

    def shutdown(self, **kwargs):
        self.shutdown_args = kwargs


class FakeDownloader:
    def __init__(self):
        self.cancel_calls = 0

    def cancel(self):
        self.cancel_calls += 1


class GuiLifecycleTests(unittest.TestCase):
    def test_close_cancels_pending_jobs_downloads_and_thumbnail_executor(self):
        app = object.__new__(MediaDownloaderApp)
        app.root = FakeRoot()
        app._media_preview_generation = 4
        app._media_preview_after = "preview"
        app._hero_animation_job = "hero"
        app._page_animation_job = "page"
        app.cancel_requested = threading.Event()
        app.active_downloaders_lock = threading.Lock()
        downloader = FakeDownloader()
        app.active_downloaders = {"job": downloader}
        app.downloader = downloader
        app._thumbnail_executor = FakeExecutor()

        app.close()

        self.assertTrue(app.root.destroyed)
        self.assertEqual(app.root.cancelled, ["preview", "hero", "page"])
        self.assertEqual(app._media_preview_generation, 5)
        self.assertTrue(app.cancel_requested.is_set())
        self.assertEqual(downloader.cancel_calls, 1)
        self.assertEqual(app._thumbnail_executor.shutdown_args, {
            "wait": False,
            "cancel_futures": True,
        })


if __name__ == "__main__":
    unittest.main()

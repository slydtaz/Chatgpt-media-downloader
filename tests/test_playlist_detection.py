import unittest
from app.gui import MediaDownloaderApp


class PlaylistDetectionTests(unittest.TestCase):
    def test_youtube_playlist_url(self):
        self.assertTrue(MediaDownloaderApp._looks_like_playlist("https://www.youtube.com/playlist?list=PL123"))

    def test_youtube_watch_with_playlist_parameter(self):
        self.assertTrue(MediaDownloaderApp._looks_like_playlist("https://www.youtube.com/watch?v=abc&list=PL123"))

    def test_single_video_is_not_playlist(self):
        self.assertFalse(MediaDownloaderApp._looks_like_playlist("https://www.youtube.com/watch?v=abc"))

    def test_generic_playlist_path(self):
        self.assertTrue(MediaDownloaderApp._looks_like_playlist("https://example.com/playlist/abc"))


if __name__ == "__main__":
    unittest.main()

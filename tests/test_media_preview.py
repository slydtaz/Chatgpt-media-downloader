import unittest
from unittest import mock

from app.media_preview import (
    MediaPreview,
    choose_thumbnail_url,
    is_safe_media_url,
    is_safe_thumbnail_url,
)


class PreviewUrlSafetyTests(unittest.TestCase):
    def test_https_thumbnail_url_is_allowed_syntactically(self):
        self.assertTrue(is_safe_thumbnail_url(
            "https://i.ytimg.com/vi/aqz-KE-bpKQ/mqdefault.jpg",
            resolve_dns=False,
        ))

    def test_http_thumbnail_is_rejected(self):
        self.assertFalse(is_safe_thumbnail_url(
            "http://i.ytimg.com/vi/aqz-KE-bpKQ/mqdefault.jpg",
            resolve_dns=False,
        ))

    def test_credentials_local_hosts_and_nonstandard_ports_are_rejected(self):
        for url in (
            "https://user:pass@i.ytimg.com/image.jpg",
            "https://localhost/image.jpg",
            "https://service.local/image.jpg",
            "https://127.0.0.1/image.jpg",
            "https://i.ytimg.com:8443/image.jpg",
        ):
            with self.subTest(url=url):
                self.assertFalse(is_safe_thumbnail_url(url, resolve_dns=False))

    def test_private_literal_media_hosts_are_rejected(self):
        for url in (
            "http://127.0.0.1/video",
            "http://192.168.1.4/video",
            "https://[::1]/video",
        ):
            with self.subTest(url=url):
                self.assertFalse(is_safe_media_url(url, resolve_dns=False))

    def test_media_url_accepts_public_syntax(self):
        self.assertTrue(is_safe_media_url(
            "https://www.youtube.com/watch?v=aqz-KE-bpKQ",
            resolve_dns=False,
        ))

    def test_largest_safe_thumbnail_is_selected(self):
        payload = {
            "thumbnail": "https://i.ytimg.com/small.jpg",
            "thumbnails": [
                {"url": "https://i.ytimg.com/large.jpg", "width": 1280, "height": 720},
                {"url": "http://i.ytimg.com/unsafe.jpg", "width": 1920, "height": 1080},
                {"url": "https://i.ytimg.com/medium.jpg", "width": 640, "height": 360},
            ],
        }
        self.assertEqual(
            choose_thumbnail_url(payload),
            "https://i.ytimg.com/large.jpg",
        )

    def test_youtube_fallback_is_built_only_for_youtube_id(self):
        payload = {"id": "aqz-KE-bpKQ", "extractor_key": "Youtube"}
        self.assertEqual(
            choose_thumbnail_url(payload, "https://youtube.com/watch?v=aqz-KE-bpKQ"),
            "https://i.ytimg.com/vi/aqz-KE-bpKQ/mqdefault.jpg",
        )
        self.assertEqual(
            choose_thumbnail_url({"id": "../private"}, "https://example.org/video"),
            "",
        )
        self.assertEqual(
            choose_thumbnail_url({"id": "aqz-KE-bpKQ"}, "https://notyoutube.com/video"),
            "",
        )

    def test_preview_model_keeps_metadata_and_bytes(self):
        preview = MediaPreview("https://example.com/v", "Example", "Channel", 12.5, "", b"png")
        self.assertEqual((preview.title, preview.creator, preview.duration), ("Example", "Channel", 12.5))
        self.assertEqual(preview.thumbnail_bytes, b"png")



if __name__ == "__main__":
    unittest.main()

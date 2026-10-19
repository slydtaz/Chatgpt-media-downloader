import tempfile
import unittest
from pathlib import Path

from app.security import (
    redact_sensitive, redacted_url, safe_archive_member_path,
    safe_filename_part, validate_url,
)


class SecurityTests(unittest.TestCase):
    def test_validate_url_accepts_http_and_https(self):
        self.assertTrue(validate_url("https://example.com/video")[0])
        self.assertTrue(validate_url("http://127.0.0.1:8080/media")[0])

    def test_validate_url_rejects_unsafe_or_malformed_authorities(self):
        for value in (
            "ftp://example.com/video",
            "not-a-url",
            "file:///etc/passwd",
            "https://user:password@example.com/media",
            "https://example.com:99999/media",
            "https://exa_mple.com/media",
            "https://example.com/a b",
            "https://example.com/\nvideo",
        ):
            with self.subTest(value=value):
                self.assertFalse(validate_url(value)[0], value)

    def test_redaction_removes_query_secrets_and_embedded_credentials(self):
        value = redact_sensitive("Fetch https://user:password@example.com/file?token=SECRET&x=1")
        self.assertNotIn("SECRET", value)
        self.assertNotIn("password", value)
        self.assertNotIn("user:", value)
        self.assertNotIn("token=SECRET", value)
        self.assertIn("example.com/<url-omitida>", value)

    def test_redacted_url_handles_ipv6_without_userinfo(self):
        self.assertEqual(
            redacted_url("https://user:secret@[2001:db8::1]:8443/private?token=x"),
            "https://[2001:db8::1]:8443/<url-omitida>",
        )

    def test_safe_archive_member_path_accepts_children(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "extract"
            root.mkdir()
            self.assertEqual(safe_archive_member_path(root, "media/tool.exe"), root / "media" / "tool.exe")

    def test_safe_archive_member_path_rejects_traversal_and_absolute_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "extract"
            root.mkdir()
            for name in ("../outside.exe", "..\\outside.exe", "/outside.exe", "C:\\outside.exe", "media/../../outside.exe"):
                with self.subTest(name=name):
                    with self.assertRaises(ValueError):
                        safe_archive_member_path(root, name)

    def test_filename(self):
        value = safe_filename_part('A<>:"/\\\\|?*B')
        self.assertNotRegex(value, r'[<>:"/\\\\|?*]')
        self.assertLessEqual(len(value.encode("utf-8")), 200)


if __name__ == "__main__":
    unittest.main()

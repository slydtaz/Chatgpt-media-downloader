import tempfile
import io
import stat
import zipfile
import urllib.error
import urllib.request
import unittest
from unittest import mock
from pathlib import Path

from app.security import (
    redact_sensitive, redacted_url, safe_archive_member_path, safe_extract_zip,
    RestrictedHTTPSRedirectHandler, safe_filename_part, trusted_urlopen, validate_url,
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

    def test_trusted_urlopen_rejects_untrusted_initial_url_before_network(self):
        with mock.patch("urllib.request.build_opener") as build_opener:
            for url in (
                "http://github.com/payload.exe",
                "https://attacker.example/payload.exe",
                "https://github.com:444/payload.exe",
                "https://user@github.com/payload.exe",
            ):
                with self.subTest(url=url):
                    with self.assertRaises(urllib.error.URLError):
                        trusted_urlopen(url, allowed_hosts={"github.com"})
            build_opener.assert_not_called()

    def test_redirect_handler_rejects_untrusted_destination_before_following(self):
        handler = RestrictedHTTPSRedirectHandler({"github.com", "objects.githubusercontent.com"})
        request = urllib.request.Request("https://github.com/org/repo/releases/download/v1/tool.exe")
        for target in (
            "http://github.com/tool.exe",
            "https://attacker.example/payload.exe",
            "https://github.com.attacker.example/payload.exe",
            "https://user@github.com/payload.exe",
            "https://github.com:444/payload.exe",
        ):
            with self.subTest(target=target):
                with self.assertRaises(urllib.error.HTTPError):
                    handler.redirect_request(request, io.BytesIO(b""), 302, "Found", {}, target)

    def test_redirect_handler_allows_official_github_cdn(self):
        handler = RestrictedHTTPSRedirectHandler({"github.com", "objects.githubusercontent.com"})
        request = urllib.request.Request("https://github.com/org/repo/releases/download/v1/tool.exe")
        redirected = handler.redirect_request(
            request, io.BytesIO(b""), 302, "Found", {}, "https://objects.githubusercontent.com/payload"
        )
        self.assertEqual(redirected.full_url, "https://objects.githubusercontent.com/payload")

    def test_safe_archive_member_path_accepts_children(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "extract"
            root.mkdir()
            self.assertEqual(safe_archive_member_path(root, "media/tool.exe"), (root / "media" / "tool.exe").resolve())

    def test_safe_archive_member_path_rejects_traversal_and_absolute_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "extract"
            root.mkdir()
            for name in ("../outside.exe", "..\\outside.exe", "/outside.exe", "C:\\outside.exe", "media/../../outside.exe"):
                with self.subTest(name=name):
                    with self.assertRaises(ValueError):
                        safe_archive_member_path(root, name)

    def test_safe_archive_member_path_rejects_ads_devices_and_ambiguous_components(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "extract"
            root.mkdir()
            for name in (
                "media/file.exe:payload",
                "media/CON.txt",
                "media/NUL",
                "media/trailing.",
                "media/trailing ",
                "media//empty.exe",
                "media/./child.exe",
                "media\\child.exe",
                "media/with<angle>.exe",
                "media/name\x01.exe",
            ):
                with self.subTest(name=name):
                    with self.assertRaises(ValueError):
                        safe_archive_member_path(root, name)

    def test_safe_archive_member_path_allows_explicit_directory_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "extract"
            root.mkdir()
            self.assertEqual(
                safe_archive_member_path(root, "media/tools/"),
                (root / "media" / "tools").resolve(),
            )

    def test_safe_extract_zip_extracts_regular_nested_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "bundle.zip"
            destination = root / "extract"
            destination.mkdir()
            with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                zf.writestr("folder/tool.txt", "trusted data")
                zf.writestr("folder/sub/", "")
            safe_extract_zip(archive, destination, max_members=20, max_unpacked_bytes=1024)
            self.assertEqual((destination / "folder" / "tool.txt").read_text(), "trusted data")
            self.assertTrue((destination / "folder" / "sub").is_dir())

    def test_safe_extract_zip_rejects_traversal_before_writing_anything(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "payload.zip"
            destination = root / "extract"
            escaped = root / "escaped.txt"
            destination.mkdir()
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("safe.txt", "should not be written")
                zf.writestr("../escaped.txt", "outside")
            with self.assertRaises(ValueError):
                safe_extract_zip(archive, destination)
            self.assertEqual(list(destination.iterdir()), [])
            self.assertFalse(escaped.exists())

    def test_safe_extract_zip_rejects_case_collisions_file_directory_conflicts_and_symlinks(self):
        builders = (
            (("item.txt", b"a"), ("ITEM.TXT", b"b")),
            (("folder/child.txt", b"a"), ("folder", b"not a directory")),
        )
        for entries in builders:
            with self.subTest(entries=entries), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                archive = root / "payload.zip"
                destination = root / "extract"
                destination.mkdir()
                with zipfile.ZipFile(archive, "w") as zf:
                    for name, data in entries:
                        zf.writestr(name, data)
                with self.assertRaises(ValueError):
                    safe_extract_zip(archive, destination)
                self.assertEqual(list(destination.iterdir()), [])

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "symlink.zip"
            destination = root / "extract"
            destination.mkdir()
            info = zipfile.ZipInfo("link")
            info.create_system = 3
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr(info, "../target")
            with self.assertRaises(ValueError):
                safe_extract_zip(archive, destination)
            self.assertEqual(list(destination.iterdir()), [])

    def test_safe_extract_zip_enforces_size_limits_and_requires_empty_destination(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "payload.zip"
            destination = root / "extract"
            destination.mkdir()
            with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                zf.writestr("large.txt", "x" * 128)
            with self.assertRaises(ValueError):
                safe_extract_zip(archive, destination, max_unpacked_bytes=32)
            self.assertEqual(list(destination.iterdir()), [])
            (destination / "keep.txt").write_text("keep")
            with self.assertRaises(ValueError):
                safe_extract_zip(archive, destination)
            self.assertEqual((destination / "keep.txt").read_text(), "keep")

    def test_filename(self):
        value = safe_filename_part('A<>:"/\\\\|?*B')
        self.assertNotRegex(value, r'[<>:"/\\\\|?*]')
        self.assertLessEqual(len(value.encode("utf-8")), 200)


if __name__ == "__main__":
    unittest.main()

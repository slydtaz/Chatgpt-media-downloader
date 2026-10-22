import base64
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import backgrounds


# Valid 1x1 PNG bytes, used only for file-signature/storage tests.
_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jHMcAAAAASUVORK5CYII="
)


class BackgroundLibraryTests(unittest.TestCase):
    def _isolated_store(self, root: Path):
        return (
            patch("app.backgrounds.APP_DATA", root),
            patch("app.backgrounds.ensure_dirs"),
        )

    def test_import_copies_image_and_records_sha256(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "wallpaper.png"
            source.write_bytes(_PNG)
            patches = self._isolated_store(root / "profile")
            with patches[0], patches[1]:
                record = backgrounds.import_file(source)
                self.assertEqual(record["kind"], "image")
                self.assertEqual(record["sha256"], backgrounds._hash_file(
                    backgrounds.background_store_dir() / record["file"]
                ))
                self.assertTrue(backgrounds.list_assets()[0]["valid"])
                resolved_record, resolved_path = backgrounds.resolve_asset(record["id"])
                self.assertEqual(resolved_record["id"], record["id"])
                self.assertTrue(resolved_path.is_file())
                self.assertNotEqual(resolved_path, source)

    def test_import_rejects_executable_and_html_signatures(self):
        bad_samples = [
            ("payload.exe", b"MZ" + b"\x00" * 80),
            ("page.html", b"<!doctype html>" + b" " * 40),
            ("vector.svg", b"<svg xmlns='http://www.w3.org/2000/svg'>" + b" " * 40),
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            patches = self._isolated_store(root / "profile")
            with patches[0], patches[1]:
                for filename, payload in bad_samples:
                    with self.subTest(filename=filename):
                        source = root / filename
                        source.write_bytes(payload)
                        with self.assertRaises(ValueError):
                            backgrounds.import_file(source)
                self.assertEqual(backgrounds.list_assets(), [])

    def test_tampered_asset_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "wallpaper.png"
            source.write_bytes(_PNG)
            patches = self._isolated_store(root / "profile")
            with patches[0], patches[1]:
                record = backgrounds.import_file(source)
                stored = backgrounds.background_store_dir() / record["file"]
                data = bytearray(stored.read_bytes())
                data[-3] ^= 1
                stored.write_bytes(data)
                self.assertFalse(backgrounds.list_assets()[0]["valid"])
                with self.assertRaisesRegex(ValueError, "SHA-256"):
                    backgrounds.resolve_asset(record["id"])

    def test_url_import_rejects_loopback_and_non_https(self):
        with self.assertRaises(ValueError):
            backgrounds._validate_public_https_url("https://127.0.0.1/wallpaper.png")
        with self.assertRaises(ValueError):
            backgrounds._validate_public_https_url("http://example.com/wallpaper.png")

    def test_delete_only_removes_registered_asset(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "wallpaper.png"
            source.write_bytes(_PNG)
            patches = self._isolated_store(root / "profile")
            with patches[0], patches[1]:
                record = backgrounds.import_file(source)
                stored = backgrounds.background_store_dir() / record["file"]
                self.assertTrue(stored.exists())
                backgrounds.delete_asset(record["id"])
                self.assertFalse(stored.exists())
                self.assertEqual(backgrounds.list_assets(), [])


if __name__ == "__main__":
    unittest.main()

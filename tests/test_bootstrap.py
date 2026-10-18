import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import bootstrap
from app.platform import SystemInfo


class BootstrapTests(unittest.TestCase):
    def test_unique_folder_contains_product_id_and_install_id(self):
        system = SystemInfo("Windows", "Windows x64", "x64", "Windows x64", "AMD64", 64)
        path = bootstrap.preferred_install_root("ABCDEF12-3456-7890-ABCD-1234567890AB", system)
        self.assertIn(bootstrap.INSTALL_FOLDER_PREFIX, str(path))
        self.assertIn("ABCDEF12-345", str(path))

    def test_owned_marker_is_required(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            marker = root / bootstrap.INSTALL_MARKER
            marker.write_text(json.dumps({"vendor": bootstrap.VENDOR if hasattr(bootstrap, "VENDOR") else "ChatGPT", "product_id": bootstrap.PRODUCT_ID, "install_id": "ABCD"}), encoding="utf-8")
            with patch.object(bootstrap, "VENDOR", "ChatGPT", create=True):
                self.assertTrue(bootstrap._is_ours(root, "ABCD"))

    def test_windows_program_files_prefers_64bit_location(self):
        with patch.dict(bootstrap.os.environ, {"ProgramW6432": r"C:\Program Files", "ProgramFiles": r"C:\Program Files (x86)"}, clear=False):
            self.assertEqual(bootstrap._windows_program_files(), Path(r"C:\Program Files"))

    def test_owned_install_candidates_require_marker_and_product(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            pf = root / "ChatGPT"
            pf.mkdir()
            old = pf / (bootstrap.INSTALL_FOLDER_PREFIX + "OLD123")
            old.mkdir()
            (old / bootstrap.INSTALL_MARKER).write_text(json.dumps({
                "vendor": "ChatGPT", "product_id": bootstrap.PRODUCT_ID, "install_id": "OLD123"
            }), encoding="utf-8")
            not_ours = pf / (bootstrap.INSTALL_FOLDER_PREFIX + "FOREIGN")
            not_ours.mkdir()
            (not_ours / bootstrap.INSTALL_MARKER).write_text(json.dumps({
                "vendor": "Other", "product_id": "com.other.app", "install_id": "FOREIGN"
            }), encoding="utf-8")
            system = SystemInfo("Windows", "Windows x64", "x64", "Windows x64", "AMD64", 64)
            with patch.object(bootstrap, "_windows_program_files", return_value=root), patch.dict(bootstrap.os.environ, {"ProgramW6432": str(root), "ProgramFiles(x86)": str(root)}, clear=False):
                found = bootstrap._owned_install_candidates(system)
            self.assertIn(old, found)
            self.assertNotIn(not_ours, found)


    def _make_project_source(self, source: Path):
        (source / "app").mkdir(parents=True)
        (source / "app" / "main.py").write_text("# main\n", encoding="utf-8")
        (source / "app" / "bootstrap.py").write_text("# bootstrap\n", encoding="utf-8")
        (source / "launcher.vbs").write_text("' launcher\n", encoding="utf-8")
        (source / "launcher.sh").write_text("#!/bin/sh\n", encoding="utf-8")
        (source / "PROJECT_ID").write_text(bootstrap.PRODUCT_ID + "\n", encoding="utf-8")

    def test_transactional_upgrade_replaces_only_after_validation(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "new-source"
            source.mkdir()
            self._make_project_source(source)
            destination = root / (bootstrap.INSTALL_FOLDER_PREFIX + "ABCDEF123456")
            destination.mkdir()
            (destination / bootstrap.INSTALL_MARKER).write_text(json.dumps({
                "vendor": "ChatGPT", "product_id": bootstrap.PRODUCT_ID, "install_id": "OLD"
            }), encoding="utf-8")
            (destination / "old-version.txt").write_text("keep until swap", encoding="utf-8")

            bootstrap._transactional_install_copy(source, destination, "ABCDEF12-3456-7890-ABCD-1234567890AB")

            self.assertTrue((destination / "app" / "main.py").is_file())
            self.assertFalse((destination / "old-version.txt").exists())
            self.assertTrue(bootstrap._is_ours(destination, "ABCDEF12-3456-7890-ABCD-1234567890AB"))

    def test_failed_staging_does_not_destroy_old_install(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "incomplete-source"
            source.mkdir()
            (source / "PROJECT_ID").write_text(bootstrap.PRODUCT_ID, encoding="utf-8")
            destination = root / (bootstrap.INSTALL_FOLDER_PREFIX + "ABCDEF123456")
            destination.mkdir()
            (destination / bootstrap.INSTALL_MARKER).write_text(json.dumps({
                "vendor": "ChatGPT", "product_id": bootstrap.PRODUCT_ID, "install_id": "OLD"
            }), encoding="utf-8")
            sentinel = destination / "old-version.txt"
            sentinel.write_text("working version", encoding="utf-8")

            with self.assertRaises(RuntimeError):
                bootstrap._transactional_install_copy(source, destination, "ABCDEF12-3456-7890-ABCD-1234567890AB")

            self.assertEqual(sentinel.read_text(encoding="utf-8"), "working version")

    def test_remove_old_owned_installation_keeps_source(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            pf = root / "ChatGPT"
            pf.mkdir()
            old = pf / (bootstrap.INSTALL_FOLDER_PREFIX + "OLD123")
            old.mkdir()
            (old / bootstrap.INSTALL_MARKER).write_text(json.dumps({
                "vendor": "ChatGPT", "product_id": bootstrap.PRODUCT_ID, "install_id": "OLD123"
            }), encoding="utf-8")
            source = root / "new-package"
            source.mkdir()
            system = SystemInfo("Windows", "Windows x64", "x64", "Windows x64", "AMD64", 64)
            with patch.object(bootstrap, "_windows_program_files", return_value=root), patch.dict(bootstrap.os.environ, {"ProgramW6432": str(root), "ProgramFiles(x86)": str(root)}, clear=False):
                removed = bootstrap.remove_old_owned_installations(source=source, system=system)
            self.assertIn(old, removed)
            self.assertFalse(old.exists())
            self.assertTrue(source.exists())


if __name__ == "__main__":
    unittest.main()

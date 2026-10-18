from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.config import PRODUCT_ID, VENDOR
from app.uninstall import INSTALL_MARKER, _validated_paths, create_cleanup_script


class UninstallerSafetyTests(unittest.TestCase):
    def _owned_install(self, root: Path) -> Path:
        install = root / "Programs" / "ChatGPT" / "MediaDownloader"
        install.mkdir(parents=True)
        (install / INSTALL_MARKER).write_text(json.dumps({
            "vendor": VENDOR,
            "product_id": PRODUCT_ID,
            "install_id": "TEST-1234",
            "version": "5.1.2",
        }), encoding="utf-8")
        return install

    def test_owned_install_and_app_data_are_accepted(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            app_data = root / "ChatGPT" / "MediaDownloader"
            app_data.mkdir(parents=True)
            install = self._owned_install(root)
            validated_data, validated_install = _validated_paths(app_data, install)
            self.assertEqual(validated_data, app_data.resolve())
            self.assertEqual(validated_install, install.resolve())

    def test_foreign_installation_is_never_eligible_for_deletion(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            app_data = root / "ChatGPT" / "MediaDownloader"
            app_data.mkdir(parents=True)
            foreign = root / "foreign" / "MediaDownloader"
            foreign.mkdir(parents=True)
            (foreign / INSTALL_MARKER).write_text(json.dumps({
                "vendor": "Someone Else",
                "product_id": "com.example.other",
            }), encoding="utf-8")
            with self.assertRaises(ValueError):
                _validated_paths(app_data, foreign)

    def test_uninstall_script_waits_for_current_process_and_preserves_download_paths(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            app_data = root / "ChatGPT" / "MediaDownloader"
            app_data.mkdir(parents=True)
            install = self._owned_install(root)
            script = create_cleanup_script(app_data, install)
            try:
                text = script.read_text(encoding="utf-8-sig")
                self.assertIn("Get-Process -Id", text) if script.suffix == ".ps1" else self.assertIn("kill -0", text)
                self.assertIn(str(app_data), text)
                self.assertIn(str(install), text)
                self.assertNotIn("Music", text)
                self.assertNotIn("Videos", text)
            finally:
                import shutil
                shutil.rmtree(script.parent, ignore_errors=True)

    def test_app_data_path_must_match_product_layout(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            wrong = root / "Downloads" / "MediaDownloader"
            wrong.mkdir(parents=True)
            with self.assertRaises(ValueError):
                _validated_paths(wrong, None)


if __name__ == "__main__":
    unittest.main()

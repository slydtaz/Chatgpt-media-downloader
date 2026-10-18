import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import bootstrap
from app.platform import SystemInfo


class SingleExecutableInstallTests(unittest.TestCase):
    def test_self_install_copies_only_executable_and_marker(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "Downloads" / "ChatGPTMediaDownloader.exe"
            source.parent.mkdir()
            source.write_bytes(b"test executable bytes")
            preferred = root / "Program Files" / "ChatGPT" / (bootstrap.INSTALL_FOLDER_PREFIX + "ABC123DEF456")
            per_user = root / "LocalAppData" / "Programs" / "ChatGPT" / (bootstrap.INSTALL_FOLDER_PREFIX + "ABC123DEF456")
            system = SystemInfo("Windows", "Windows x64", "x64", "Windows x64", "AMD64", 64)
            with patch.object(bootstrap, "preferred_install_root", return_value=preferred), \
                 patch.object(bootstrap, "per_user_install_root", return_value=per_user), \
                 patch.object(bootstrap, "remove_old_owned_installations", return_value=[]):
                target, migrated = bootstrap.ensure_frozen_installation(source, "ABC123DEF456", system)
            self.assertTrue(migrated)
            expected_exe = "ChatGPTMediaDownloader.exe" if bootstrap.os.name == "nt" else "ChatGPTMediaDownloader"
            self.assertEqual((target / expected_exe).read_bytes(), b"test executable bytes")
            self.assertTrue(bootstrap._is_product_install(target))
            self.assertEqual(sorted(p.name for p in target.iterdir()), sorted([expected_exe, bootstrap.INSTALL_MARKER]))

    def test_frozen_install_does_not_overwrite_unowned_directory(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "ChatGPTMediaDownloader.exe"
            source.write_bytes(b"new exe")
            preferred = root / "preferred"
            preferred.mkdir()
            sentinel = preferred / "do-not-touch.txt"
            sentinel.write_text("foreign application", encoding="utf-8")
            per_user = root / "per-user"
            system = SystemInfo("Windows", "Windows x64", "x64", "Windows x64", "AMD64", 64)
            with patch.object(bootstrap, "preferred_install_root", return_value=preferred), \
                 patch.object(bootstrap, "per_user_install_root", return_value=per_user), \
                 patch.object(bootstrap, "remove_old_owned_installations", return_value=[]):
                target, migrated = bootstrap.ensure_frozen_installation(source, "ABC123DEF456", system)
            self.assertEqual(target, per_user)
            self.assertTrue(sentinel.exists())
            self.assertTrue((per_user / ("ChatGPTMediaDownloader.exe" if bootstrap.os.name == "nt" else "ChatGPTMediaDownloader")).is_file())


if __name__ == "__main__":
    unittest.main()

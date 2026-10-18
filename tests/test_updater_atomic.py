import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.locking import CrossProcessFileLock
from app.platform import SystemInfo
from app.updater import UpdateError, _replace_file_pair, _replace_single_file, install_tool_from_release


class UpdaterAtomicTests(unittest.TestCase):
    def test_single_replace_promotes_staged_file(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            target = root / "yt-dlp.exe"
            staged = root / "new.exe"
            target.write_text("old", encoding="utf-8")
            staged.write_text("new", encoding="utf-8")
            _replace_single_file(staged, target)
            self.assertEqual(target.read_text(encoding="utf-8"), "new")
            self.assertFalse(staged.exists())

    def test_failed_single_replace_keeps_previous_target(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            target = root / "yt-dlp.exe"
            staged = root / "new.exe"
            target.write_text("old", encoding="utf-8")
            staged.write_text("new", encoding="utf-8")
            with patch("app.updater.os.replace", side_effect=PermissionError("locked")):
                with self.assertRaises(PermissionError):
                    _replace_single_file(staged, target)
            self.assertEqual(target.read_text(encoding="utf-8"), "old")

    def test_ffmpeg_pair_rolls_back_if_second_promotion_fails(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            old_ffmpeg, old_probe = root / "ffmpeg", root / "ffprobe"
            new_ffmpeg, new_probe = root / "ffmpeg.new", root / "ffprobe.new"
            old_ffmpeg.write_text("old ffmpeg", encoding="utf-8")
            old_probe.write_text("old probe", encoding="utf-8")
            new_ffmpeg.write_text("new ffmpeg", encoding="utf-8")
            new_probe.write_text("new probe", encoding="utf-8")
            real_replace = os.replace

            def replace(source, target):
                if Path(source) == new_probe and Path(target) == old_probe:
                    raise PermissionError("probe busy")
                return real_replace(source, target)

            with patch("app.updater.os.replace", side_effect=replace):
                with self.assertRaises(UpdateError):
                    _replace_file_pair(new_ffmpeg, old_ffmpeg, new_probe, old_probe)
            self.assertEqual(old_ffmpeg.read_text(encoding="utf-8"), "old ffmpeg")
            self.assertEqual(old_probe.read_text(encoding="utf-8"), "old probe")

    def test_dependency_update_is_rejected_when_shared_lock_is_held(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            lock_path = root / "dependency-update.lock"
            lock = CrossProcessFileLock(lock_path)
            self.assertTrue(lock.acquire())
            system = SystemInfo("Linux", "Linux x64", "x64", "Linux x64", "x86_64", 64)
            try:
                with patch("app.updater.APP_DATA", root), patch("app.updater._install_tool_from_release_locked") as installer:
                    with self.assertRaisesRegex(UpdateError, "Outra instância está atualizando"):
                        install_tool_from_release("yt-dlp", system)
                    installer.assert_not_called()
            finally:
                lock.release()


if __name__ == "__main__":
    unittest.main()

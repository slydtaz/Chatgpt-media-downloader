import io
import stat
import os
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from pathlib import Path

from app.dependencies import _candidate_names, extract_archive
from app.platform import SystemInfo


class DependencyTests(unittest.TestCase):
    def make(self, os_name, arch):
        return SystemInfo(os_name, f"{os_name} {arch}", arch, f"{os_name} {arch}", arch, 64)

    def test_windows_x86_name(self):
        self.assertEqual(_candidate_names("yt-dlp", self.make("Windows", "x86"))[0], "yt-dlp_x86.exe")

    def test_windows_arm64_name(self):
        self.assertEqual(_candidate_names("yt-dlp", self.make("Windows", "ARM64"))[0], "yt-dlp_arm64.exe")

    def test_linux_armv7_name(self):
        self.assertIn("yt-dlp_linux_armv7l.zip", _candidate_names("yt-dlp", self.make("Linux", "ARMv7")))

    def test_extract_archive_accepts_expected_media_tool(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "tools.zip"
            destination = root / "tools"
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("release/bin/ffmpeg.exe", b"test-tool")
            extract_archive(archive, destination)
            self.assertEqual((destination / "ffmpeg.exe").read_bytes(), b"test-tool")

    @unittest.skipIf(os.name == "nt", "Symlink creation may require elevated privileges on Windows.")
    def test_extract_archive_does_not_follow_existing_destination_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "tools.zip"
            outside = root / "outside.txt"
            outside.write_text("preserve", encoding="utf-8")
            destination = root / "tools"
            destination.mkdir()
            try:
                (destination / "ffmpeg.exe").symlink_to(outside)
            except OSError:
                self.skipTest("Symlinks are not available in this environment.")
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("release/ffmpeg.exe", b"replacement")
            with self.assertRaises(ValueError):
                extract_archive(archive, destination)
            self.assertEqual(outside.read_text(encoding="utf-8"), "preserve")

    @unittest.skipIf(os.name == "nt", "Symlink creation may require elevated privileges on Windows.")
    def test_extract_archive_isolated_from_stale_extracting_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "tools.zip"
            outside = root / "outside"
            outside.mkdir()
            destination = root / "tools"
            destination.mkdir()
            (destination / ".extracting").symlink_to(outside, target_is_directory=True)
            (outside / "sentinel.txt").write_text("preserve", encoding="utf-8")
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("release/ffmpeg.exe", b"tool")
            extract_archive(archive, destination)
            self.assertEqual((outside / "sentinel.txt").read_text(encoding="utf-8"), "preserve")
            self.assertEqual((destination / "ffmpeg.exe").read_bytes(), b"tool")

    def test_extract_archive_rejects_duplicate_member_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "duplicate.zip"
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("release/ffmpeg.exe", b"first")
                zf.writestr("release/ffmpeg.exe", b"second")
            with self.assertRaises(ValueError):
                extract_archive(archive, root / "tools")

    def test_extract_archive_rolls_back_if_second_tool_replacement_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "tools.zip"
            destination = root / "tools"
            destination.mkdir()
            (destination / "ffmpeg.exe").write_bytes(b"old-ffmpeg")
            (destination / "ffprobe.exe").write_bytes(b"old-ffprobe")
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("release/bin/ffmpeg.exe", b"new-ffmpeg")
                zf.writestr("release/bin/ffprobe.exe", b"new-ffprobe")

            real_replace = os.replace

            def fail_ffprobe_promotion(source, target):
                source_path, target_path = Path(source), Path(target)
                if target_path.name == "ffprobe.exe" and source_path.name.endswith(".staged"):
                    raise OSError("simulated disk or permission failure")
                return real_replace(source, target)

            with patch("app.dependencies.os.replace", side_effect=fail_ffprobe_promotion):
                with self.assertRaises(ValueError):
                    extract_archive(archive, destination)

            self.assertEqual((destination / "ffmpeg.exe").read_bytes(), b"old-ffmpeg")
            self.assertEqual((destination / "ffprobe.exe").read_bytes(), b"old-ffprobe")
            self.assertFalse(list(destination.glob("*.staged")))

    def test_extract_archive_rejects_duplicate_tool_basenames(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "duplicate-tools.zip"
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("one/ffmpeg.exe", b"first")
                zf.writestr("two/ffmpeg.exe", b"second")
            with self.assertRaises(ValueError):
                extract_archive(archive, root / "tools")

    def test_extract_archive_reports_corrupt_zip_as_value_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "corrupt.zip"
            archive.write_bytes(b"not a zip archive")
            with self.assertRaises(ValueError):
                extract_archive(archive, root / "tools")

    def test_extract_archive_rejects_oversized_compressed_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "tools.zip"
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("release/ffmpeg.exe", b"small executable")
            with patch("app.dependencies.MAX_ARCHIVE_COMPRESSED_BYTES", 1):
                with self.assertRaises(ValueError):
                    extract_archive(archive, root / "tools")

    @unittest.skipIf(os.name == "nt", "Symlink creation may require elevated privileges on Windows.")
    def test_extract_archive_rejects_destination_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "tools.zip"
            outside = root / "outside"
            outside.mkdir()
            (outside / "sentinel.txt").write_text("preserve", encoding="utf-8")
            destination = root / "tools"
            destination.symlink_to(outside, target_is_directory=True)
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("release/ffmpeg.exe", b"replacement")
            with self.assertRaises(ValueError):
                extract_archive(archive, destination)
            self.assertEqual((outside / "sentinel.txt").read_text(encoding="utf-8"), "preserve")
            self.assertFalse((outside / "ffmpeg.exe").exists())

    def test_extract_archive_rejects_missing_or_unrecognized_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "empty-tool.zip"
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("release/readme.txt", "not a tool")
            with self.assertRaises(ValueError):
                extract_archive(archive, root / "tools")

    def test_extract_archive_rejects_zip_path_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "malicious.zip"
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("../outside.txt", "not allowed")
            with self.assertRaises(ValueError):
                extract_archive(archive, root / "tools")
            self.assertFalse((root / "outside.txt").exists())

    def test_extract_archive_rejects_zip_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "malicious.zip"
            info = zipfile.ZipInfo("release/ffmpeg.exe")
            info.create_system = 3
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr(info, "../../outside.txt")
            with self.assertRaises(ValueError):
                extract_archive(archive, root / "tools")
            self.assertFalse((root / "outside.txt").exists())


    def test_extract_archive_rejects_excessive_unpacked_size(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "oversized.zip"
            with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                zf.writestr("release/ffmpeg.exe", b"x" * 20)
            with patch("app.dependencies.MAX_ARCHIVE_UNPACKED_BYTES", 10):
                with self.assertRaises(ValueError):
                    extract_archive(archive, root / "tools")

    def test_extract_archive_rejects_tar_links(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "malicious.tar.xz"
            with tarfile.open(archive, "w:xz") as tf:
                info = tarfile.TarInfo("release/ffmpeg")
                info.type = tarfile.SYMTYPE
                info.linkname = "../../outside.txt"
                tf.addfile(info)
            with self.assertRaises(ValueError):
                extract_archive(archive, root / "tools")
            self.assertFalse((root / "outside.txt").exists())


if __name__ == "__main__":
    unittest.main()

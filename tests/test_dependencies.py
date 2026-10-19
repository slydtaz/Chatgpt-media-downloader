import io
import stat
import tarfile
import tempfile
import unittest
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

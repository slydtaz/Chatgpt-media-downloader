import unittest

from app.dependencies import _candidate_names
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


if __name__ == "__main__":
    unittest.main()

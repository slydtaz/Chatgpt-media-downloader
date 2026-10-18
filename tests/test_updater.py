import unittest

from app.platform import SystemInfo
from app.updater import ff_asset_name, yt_asset_name


class UpdaterMappingTests(unittest.TestCase):
    def make(self, os_name, arch):
        label = f"{os_name} {arch}"
        return SystemInfo(os_name, label, arch, label, arch, 64)

    def test_windows_x86_uses_official_yt_asset(self):
        self.assertEqual(yt_asset_name(self.make("Windows", "x86")), "yt-dlp_x86.exe")
        self.assertIsNone(ff_asset_name(self.make("Windows", "x86")))

    def test_windows_x64(self):
        self.assertEqual(yt_asset_name(self.make("Windows", "x64")), "yt-dlp.exe")
        self.assertEqual(ff_asset_name(self.make("Windows", "x64")), "ffmpeg-master-latest-win64-gpl.zip")

    def test_windows_arm64(self):
        self.assertEqual(yt_asset_name(self.make("Windows", "ARM64")), "yt-dlp_arm64.exe")
        self.assertEqual(ff_asset_name(self.make("Windows", "ARM64")), "ffmpeg-master-latest-winarm64-gpl.zip")

    def test_linux_armv7(self):
        self.assertEqual(yt_asset_name(self.make("Linux", "ARMv7")), "yt-dlp_linux_armv7l.zip")
        self.assertIsNone(ff_asset_name(self.make("Linux", "ARMv7")))

    def test_macos_universal(self):
        self.assertEqual(yt_asset_name(self.make("Darwin", "Intel")), "yt-dlp_macos")
        self.assertEqual(yt_asset_name(self.make("Darwin", "Apple Silicon")), "yt-dlp_macos")
        self.assertIsNone(ff_asset_name(self.make("Darwin", "Intel")))


if __name__ == "__main__":
    unittest.main()

import hashlib
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


from app.platform import SystemInfo
from app.updater import (
    ReleaseAsset, _trusted_github_api_url, _trusted_github_url, _verify_checksum,
    ff_asset_name, yt_asset_name,
)


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



class DependencyDownloadTrustTests(unittest.TestCase):
    def test_only_https_github_asset_hosts_are_allowed(self):
        for url in (
            "https://github.com/yt-dlp/yt-dlp/releases/download/v1/tool.exe",
            "https://objects.githubusercontent.com/assets/tool.exe",
            "https://release-assets.githubusercontent.com/assets/tool.exe",
        ):
            with self.subTest(url=url):
                self.assertTrue(_trusted_github_url(url))
        for url in (
            "http://github.com/tool.exe",
            "https://github.com.attacker.example/tool.exe",
            "https://attacker.example@github.com/tool.exe",
            "https://github.com:444/tool.exe",
            "https://github.com./tool.exe",
            "file:///tmp/tool.exe",
        ):
            with self.subTest(url=url):
                self.assertFalse(_trusted_github_url(url))


    def test_release_metadata_is_limited_to_the_official_github_api(self):
        self.assertTrue(_trusted_github_api_url("https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest"))
        for url in (
            "http://api.github.com/repos/yt-dlp/yt-dlp/releases/latest",
            "https://api.github.com.attacker.example/repos/yt-dlp/yt-dlp/releases/latest",
            "https://api.github.com:444/repos/yt-dlp/yt-dlp/releases/latest",
            "https://user@api.github.com/repos/yt-dlp/yt-dlp/releases/latest",
        ):
            with self.subTest(url=url):
                self.assertFalse(_trusted_github_api_url(url))

    def test_missing_upstream_checksum_manifest_fails_closed(self):
        asset = ReleaseAsset("tool.exe", "https://github.com/project/tool/releases/download/v1/tool.exe", 4)
        with TemporaryDirectory() as tmp:
            file = Path(tmp) / "tool.exe"
            file.write_bytes(b"tool")
            self.assertFalse(_verify_checksum({"assets": []}, asset, file))

    def test_checksum_manifest_must_match_exact_sha256(self):
        payload = b"trusted media tool"
        digest = hashlib.sha256(payload).hexdigest()
        asset = ReleaseAsset("tool.exe", "https://github.com/project/tool/releases/download/v1/tool.exe", len(payload))
        manifest_text = f"{digest}  tool.exe\n"
        checksum = ReleaseAsset("SHA2-256SUMS", "https://github.com/project/tool/releases/download/v1/SHA2-256SUMS", len(manifest_text.encode()))
        release = {"assets": [{"name": checksum.name, "browser_download_url": checksum.url, "size": checksum.size}]}
        with TemporaryDirectory() as tmp:
            file = Path(tmp) / asset.name
            file.write_bytes(payload)

            def write_manifest(url, destination, **kwargs):
                destination.write_text(manifest_text, encoding="utf-8")

            with patch("app.updater._download", side_effect=write_manifest):
                self.assertTrue(_verify_checksum(release, asset, file))
            file.write_bytes(b"tampered data")
            with patch("app.updater._download", side_effect=write_manifest):
                self.assertFalse(_verify_checksum(release, asset, file))


if __name__ == "__main__":
    unittest.main()

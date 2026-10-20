from __future__ import annotations

import hashlib
import os
import json
import shutil
import subprocess
import tempfile
import unittest
import io
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from unittest.mock import patch

from app.app_update import (
    API_ROOT,
    AppUpdateError,
    _release_candidate,
    _windows_update_helper_script,
    _safe_extract_zip,
    _stage_source_tree,
    _verify_executable_hash,
    _trusted_url,
    AppUpdate,
    check_for_update,
    check_repair_candidate,
    is_newer_version,
    version_key,
)
from app.config import PRODUCT_ID
from app.security import RestrictedHTTPSRedirectHandler



class TrustedUpdateUrlTests(unittest.TestCase):
    def test_release_urls_require_https_trusted_host_and_standard_port(self):
        self.assertTrue(_trusted_url("https://github.com/slydtaz/Chatgpt-media-downloader/releases/latest"))
        self.assertTrue(_trusted_url("https://api.github.com/repos/slydtaz/Chatgpt-media-downloader/releases/latest", metadata=True))
        for value in (
            "http://github.com/slydtaz/Chatgpt-media-downloader",
            "https://user:password@github.com/slydtaz/Chatgpt-media-downloader",
            "https://github.com:444/slydtaz/Chatgpt-media-downloader",
            "https://github.com.attacker.example/slydtaz/Chatgpt-media-downloader",
        ):
            with self.subTest(value=value):
                self.assertFalse(_trusted_url(value, metadata=True))
        self.assertFalse(_trusted_url("https://api.github.com/repos/owner/repo"))


class UpdateRedirectSafetyTests(unittest.TestCase):
    def test_redirect_handler_rejects_untrusted_host_and_http_downgrade(self):
        handler = RestrictedHTTPSRedirectHandler({
            "github.com", "objects.githubusercontent.com", "release-assets.githubusercontent.com",
        })
        request = urllib.request.Request(
            "https://github.com/slydtaz/Chatgpt-media-downloader/releases/download/v5.3.1/ChatGPTMediaDownloader.exe"
        )
        for target in (
            "http://github.com/download.exe",
            "https://attacker.example/download.exe",
            "https://github.com.attacker.example/download.exe",
        ):
            with self.subTest(target=target):
                with self.assertRaises(urllib.error.HTTPError):
                    handler.redirect_request(request, io.BytesIO(b""), 302, "Found", {}, target)


class VersionComparisonTests(unittest.TestCase):
    def test_semver_like_versions_compare_numerically(self):
        self.assertTrue(is_newer_version("5.0.0", "4.9.0"))
        self.assertTrue(is_newer_version("4.10.0", "4.9.0"))
        self.assertFalse(is_newer_version("4.9.0", "4.9.0"))
        self.assertFalse(is_newer_version("4.8.9", "4.9.0"))
        self.assertEqual(version_key("v5.12.3"), (5, 12, 3))
        self.assertTrue(is_newer_version("5.4.0", "5.4.0-beta.1"))
        self.assertTrue(is_newer_version("5.4.0-beta.2", "5.4.0-beta.1"))
        self.assertFalse(is_newer_version("5.4.0-beta.1", "5.4.0"))
        self.assertTrue(is_newer_version("5.4.0-rc.1", "5.4.0-beta.9"))
        self.assertTrue(is_newer_version("5.4.0-beta.1", "5.3.2"))
        self.assertFalse(is_newer_version("5.4.0-beta.2", "5.4.0-beta.10"))



class AppUpdateDiscoveryTests(unittest.TestCase):
    def test_source_install_uses_main_branch_when_no_release_is_published(self):
        with patch("app.app_update._request_json", return_value=None), \
             patch("app.app_update._source_version", return_value="5.0.0"), \
             patch("app.app_update._source_notes", return_value="Atualizações e reparos"):
            update = check_for_update("4.9.0", frozen=False)
        self.assertIsNotNone(update)
        self.assertEqual(update.kind, "source")
        self.assertEqual(update.version, "5.0.0")
        self.assertEqual(update.source_ref, "main")

    def test_sha256_is_required_to_verify_executable(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            staged = root / "ChatGPTMediaDownloader.exe"
            staged.write_bytes(b"x" * (1024 * 1024 + 10))
            sha = hashlib.sha256(staged.read_bytes()).hexdigest()
            update = AppUpdate("5.0.0", "5.1.0", "executable", "https://github.com/slydtaz/Chatgpt-media-downloader/releases/download/v5.1.0/ChatGPTMediaDownloader.exe", "https://github.com/slydtaz/Chatgpt-media-downloader/releases/tag/v5.1.0", asset_sha256=sha)
            _verify_executable_hash(update, staged, sha, root)
            with self.assertRaises(AppUpdateError):
                _verify_executable_hash(update, staged, "0" * 64, root)

    def test_frozen_install_does_not_try_to_install_source_archive(self):
        with patch("app.app_update._request_json", return_value=None), \
             patch("app.app_update._source_version") as source_version:
            update = check_for_update("4.9.0", frozen=True)
        self.assertIsNone(update)
        source_version.assert_not_called()

    def test_latest_versioned_release_is_checked_before_stable_alias(self):
        stable = {
            "tag_name": "stable",
            "name": "ChatGPT Media Downloader 5.0.2 — Stable",
            "html_url": "https://github.com/slydtaz/Chatgpt-media-downloader/releases/tag/stable",
            "assets": [
                {"name": "ChatGPTMediaDownloader.exe", "browser_download_url": "https://github.com/slydtaz/Chatgpt-media-downloader/releases/download/stable/ChatGPTMediaDownloader.exe", "size": 4096, "state": "uploaded"},
                {"name": "SHA256SUMS.txt", "browser_download_url": "https://github.com/slydtaz/Chatgpt-media-downloader/releases/download/stable/SHA256SUMS.txt", "size": 90, "state": "uploaded"},
            ],
        }
        old_latest = {"tag_name": "v5.0.0", "name": "ChatGPT Media Downloader 5.0.0", "assets": []}
        with patch("app.app_update._request_json", side_effect=[old_latest, stable]) as request:
            update = check_for_update("5.0.1", frozen=True)
        self.assertIsNotNone(update)
        self.assertEqual(update.version, "5.0.2")
        self.assertEqual(update.tag_name, "stable")
        self.assertEqual(request.call_args_list[0].args[0], f"{API_ROOT}/releases/latest")
        self.assertEqual(request.call_args_list[1].args[0], f"{API_ROOT}/releases/tags/stable")


    def test_newest_versioned_release_beats_older_stable_alias(self):
        newest = {
            "tag_name": "v5.1.0",
            "name": "5.1.0 - stable",
            "html_url": "https://github.com/slydtaz/Chatgpt-media-downloader/releases/tag/v5.1.0",
            "assets": [
                {"name": "ChatGPTMediaDownloader.exe", "browser_download_url": "https://github.com/slydtaz/Chatgpt-media-downloader/releases/download/v5.1.0/ChatGPTMediaDownloader.exe", "size": 4096, "state": "uploaded"},
                {"name": "SHA256SUMS.txt", "browser_download_url": "https://github.com/slydtaz/Chatgpt-media-downloader/releases/download/v5.1.0/SHA256SUMS.txt", "size": 90, "state": "uploaded"},
            ],
        }
        with patch("app.app_update._request_json", return_value=newest) as request:
            update = check_for_update("5.0.6", frozen=True)
        self.assertIsNotNone(update)
        self.assertEqual(update.version, "5.1.0")
        self.assertEqual(update.tag_name, "v5.1.0")
        self.assertEqual(request.call_count, 1)
        self.assertEqual(request.call_args_list[0].args[0], f"{API_ROOT}/releases/latest")

    def test_executable_repair_prefers_stable_release(self):
        stable = {
            "tag_name": "stable",
            "name": "ChatGPT Media Downloader 5.0.2 — Stable",
            "html_url": "https://github.com/slydtaz/Chatgpt-media-downloader/releases/tag/stable",
            "assets": [
                {"name": "ChatGPTMediaDownloader.exe", "browser_download_url": "https://github.com/slydtaz/Chatgpt-media-downloader/releases/download/stable/ChatGPTMediaDownloader.exe", "size": 4096, "state": "uploaded"},
                {"name": "SHA256SUMS.txt", "browser_download_url": "https://github.com/slydtaz/Chatgpt-media-downloader/releases/download/stable/SHA256SUMS.txt", "size": 90, "state": "uploaded"},
            ],
        }
        with patch("app.app_update._request_json", side_effect=[None, stable]) as request:
            update = check_repair_candidate("5.0.1", frozen=True)
        self.assertEqual(update.version, "5.0.2")
        self.assertEqual(update.tag_name, "stable")
        self.assertEqual(request.call_args_list[0].args[0], f"{API_ROOT}/releases/latest")
        self.assertEqual(request.call_args_list[1].args[0], f"{API_ROOT}/releases/tags/stable")

    def test_stable_release_uses_semantic_version_from_title(self):
        release = {
            "tag_name": "stable",
            "name": "ChatGPT Media Downloader 5.0.1 — Stable",
            "html_url": "https://github.com/slydtaz/Chatgpt-media-downloader/releases/tag/stable",
            "assets": [
                {"name": "ChatGPTMediaDownloader.exe", "browser_download_url": "https://github.com/slydtaz/Chatgpt-media-downloader/releases/download/stable/ChatGPTMediaDownloader.exe", "size": 2048, "state": "uploaded"},
                {"name": "SHA256SUMS.txt", "browser_download_url": "https://github.com/slydtaz/Chatgpt-media-downloader/releases/download/stable/SHA256SUMS.txt", "size": 90, "state": "uploaded"},
            ],
        }
        update = _release_candidate("5.0.0", release, frozen=True)
        self.assertIsNotNone(update)
        self.assertEqual(update.version, "5.0.1")
        self.assertEqual(update.tag_name, "stable")

    def test_stable_tag_without_semver_in_title_is_not_an_update(self):
        release = {"tag_name": "stable", "name": "Stable release", "assets": []}
        self.assertIsNone(_release_candidate("5.0.0", release, frozen=False))

    def test_release_executable_requires_exe_and_checksum_assets(self):
        release = {
            "tag_name": "v5.1.0",
            "html_url": "https://github.com/slydtaz/Chatgpt-media-downloader/releases/tag/v5.1.0",
            "assets": [
                {"name": "ChatGPTMediaDownloader.exe", "browser_download_url": "https://github.com/slydtaz/Chatgpt-media-downloader/releases/download/v5.1.0/ChatGPTMediaDownloader.exe", "size": 2048, "state": "uploaded"},
                {"name": "SHA256SUMS.txt", "browser_download_url": "https://github.com/slydtaz/Chatgpt-media-downloader/releases/download/v5.1.0/SHA256SUMS.txt", "size": 90, "state": "uploaded"},
            ],
        }
        update = _release_candidate("5.0.0", release, frozen=True)
        self.assertIsNotNone(update)
        self.assertEqual(update.kind, "executable")
        self.assertEqual(update.version, "5.1.0")
        release["assets"] = release["assets"][:1]
        with self.assertRaises(AppUpdateError):
            _release_candidate("5.0.0", release, frozen=True)


    def test_windows_repair_helper_waits_for_startup_confirmation_and_keeps_diagnostics(self):
        script = _windows_update_helper_script()
        self.assertIn("[Parameter(Mandatory=$true)][bool]$StartupRepair", script)
        self.assertIn("while (Test-Path -LiteralPath $RepairMarker)", script)
        self.assertIn("[System.Windows.Forms.MessageBox]::Show", script)
        self.assertIn("Get-FileHash -LiteralPath", script)
        self.assertIn("preservando o backup", script)
        self.assertIn("Write-UpdateLog", script)  # persistent helper logging is present


    @unittest.skipUnless(os.name == "nt", "PowerShell syntax is checked only on Windows.")
    def test_windows_repair_helper_parses_without_powershell_errors(self):
        powershell = shutil.which("powershell.exe")
        if not powershell:
            self.skipTest("Windows PowerShell is not available in this environment.")
        with tempfile.TemporaryDirectory() as td:
            helper_path = Path(td) / "apply-update-check.ps1"
            helper_path.write_text(_windows_update_helper_script(), encoding="utf-8-sig")
            env = os.environ.copy()
            env["CGMD_HELPER_SCRIPT"] = str(helper_path)
            command = (
                "$tokens=$null; $errors=$null; "
                "[System.Management.Automation.Language.Parser]::ParseFile("
                "$env:CGMD_HELPER_SCRIPT, [ref]$tokens, [ref]$errors) | Out-Null; "
                "if ($errors.Count -gt 0) { "
                "$errors | ForEach-Object { Write-Error $_ }; exit 1 }"
            )
            result = subprocess.run(
                [powershell, "-NoProfile", "-NonInteractive", "-Command", command],
                capture_output=True,
                text=True,
                timeout=30,
                env=env,
                check=False,
            )
            self.assertEqual(result.returncode, 0, msg=result.stdout + "\n" + result.stderr)


class SafeArchiveTests(unittest.TestCase):
    def test_valid_source_archive_is_found(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            archive = root / "source.zip"
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("project/PROJECT_ID", PRODUCT_ID)
                zf.writestr("project/app/main.py", "pass")
                zf.writestr("project/app/bootstrap.py", "pass")
            extracted = root / "extracted"
            extracted.mkdir()
            with zipfile.ZipFile(archive) as zf:
                # Test ZIP path safety/extraction logic against a normal project tree.
                pass
            # The tested function expects to own extraction, so create the archive
            # directly and run it once with the expected validated structure.
            source = _safe_extract_zip(archive, extracted)
            self.assertEqual(source.name, "project")

    def test_source_update_keeps_tools_and_install_marker(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            target = root / "installed"
            source = root / "source"
            target.mkdir()
            (target / "tools").mkdir()
            (target / "tools" / "ffmpeg.exe").write_text("existing tool", encoding="utf-8")
            marker = {"vendor": "ChatGPT", "product_id": PRODUCT_ID, "install_id": "test-id", "version": "4.9.0"}
            (target / ".chatgpt-media-downloader-install.json").write_text(json.dumps(marker), encoding="utf-8")
            (source / "app").mkdir(parents=True)
            (source / "PROJECT_ID").write_text(PRODUCT_ID, encoding="utf-8")
            for name in ("main.py", "bootstrap.py"):
                (source / "app" / name).write_text("pass", encoding="utf-8")
            for name in ("launcher.vbs", "launcher.sh"):
                (source / name).write_text("launcher", encoding="utf-8")
            (source / "app" / "config.py").write_text('VERSION = "5.0.0"\n', encoding="utf-8")
            staged = _stage_source_tree(source, target, "5.0.0")
            self.assertEqual((staged / "tools" / "ffmpeg.exe").read_text(encoding="utf-8"), "existing tool")
            saved_marker = json.loads((staged / ".chatgpt-media-downloader-install.json").read_text(encoding="utf-8"))
            self.assertEqual(saved_marker["version"], "5.0.0")
            self.assertEqual(saved_marker["install_id"], "test-id")
            shutil.rmtree(staged)


    def test_archive_unpacked_size_limit_is_checked_before_extraction(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            archive = root / "oversized.zip"
            with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                zf.writestr("project/PROJECT_ID", PRODUCT_ID)
                zf.writestr("project/large.bin", b"x" * 100)
            with patch("app.app_update.MAX_SOURCE_UNPACKED_BYTES", 10):
                with self.assertRaises(AppUpdateError):
                    _safe_extract_zip(archive, root / "extract")

    def test_parent_traversal_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            archive = root / "unsafe.zip"
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("../outside.txt", "do not write")
            with self.assertRaises(AppUpdateError):
                _safe_extract_zip(archive, root / "extract")
            self.assertFalse((root / "outside.txt").exists())


if __name__ == "__main__":
    unittest.main()

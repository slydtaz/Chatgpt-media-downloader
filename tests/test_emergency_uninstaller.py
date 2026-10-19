from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from emergency_uninstaller import (
    INSTALL_MARKER,
    INSTALL_PREFIX,
    PRODUCT_ID,
    VENDOR,
    _safe_output_dir,
    discover_targets,
    perform_cleanup,
)


class EmergencyUninstallerTests(unittest.TestCase):
    def make_env(self, root: Path) -> dict[str, str]:
        home = root / "profile"
        local = home / "AppData" / "Local"
        roaming = home / "AppData" / "Roaming"
        program_files = root / "Program Files"
        one_drive = home / "OneDrive"
        for path in (home, local, roaming, program_files, one_drive):
            path.mkdir(parents=True, exist_ok=True)
        return {
            "USERPROFILE": str(home),
            "LOCALAPPDATA": str(local),
            "APPDATA": str(roaming),
            "PROGRAMDATA": str(root / "ProgramData"),
            "ProgramW6432": str(program_files),
            "ProgramFiles": str(program_files),
            "ProgramFiles(x86)": str(root / "Program Files (x86)"),
            "OneDrive": str(one_drive),
            "TEMP": str(root / "temp"),
        }

    def add_owned_install(self, parent: Path, suffix: str = "123ABC") -> Path:
        folder = parent / f"{INSTALL_PREFIX}{suffix}"
        folder.mkdir(parents=True)
        (folder / INSTALL_MARKER).write_text(json.dumps({
            "vendor": VENDOR, "product_id": PRODUCT_ID
        }), encoding="utf-8")
        return folder

    def test_discovers_only_product_prefixed_direct_install_folders(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            env = self.make_env(root)
            parent = Path(env["LOCALAPPDATA"]) / "Programs" / "ChatGPT"
            parent.mkdir(parents=True)
            owned = self.add_owned_install(parent)
            unrelated = parent / "OtherChatGPTApp"
            unrelated.mkdir()
            plan = discover_targets(env)
            self.assertIn(owned, [item.path for item in plan.install_dirs])
            self.assertNotIn(unrelated, [item.path for item in plan.install_dirs])

    def test_refuses_install_with_foreign_product_marker(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            env = self.make_env(root)
            parent = Path(env["LOCALAPPDATA"]) / "Programs" / "ChatGPT"
            parent.mkdir(parents=True)
            foreign = parent / f"{INSTALL_PREFIX}foreign"
            foreign.mkdir()
            (foreign / INSTALL_MARKER).write_text(json.dumps({
                "vendor": "OtherVendor", "product_id": "other.product"
            }), encoding="utf-8")
            plan = discover_targets(env)
            self.assertNotIn(foreign, [item.path for item in plan.install_dirs])

    def test_marks_legacy_product_named_folder_for_explicit_cleanup(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            env = self.make_env(root)
            parent = Path(env["LOCALAPPDATA"]) / "Programs" / "ChatGPT"
            parent.mkdir(parents=True)
            legacy = parent / f"{INSTALL_PREFIX}old"
            legacy.mkdir()
            plan = discover_targets(env)
            self.assertIn(legacy, [item.path for item in plan.install_dirs])
            candidate = next(item for item in plan.install_dirs if item.path == legacy)
            self.assertFalse(candidate.verified)

    def test_safe_output_path_excludes_generic_downloads_folder(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            home = root / "profile"
            home.mkdir()
            data = home / "AppData" / "Local" / "ChatGPT" / "MediaDownloader"
            data.mkdir(parents=True)
            safe, _ = _safe_output_dir(home / "Downloads", home, None, data, [])
            self.assertFalse(safe)
            safe, _ = _safe_output_dir(home / "media" / "export" / "audio", home, None, data, [])
            self.assertTrue(safe)

    def test_cleanup_removes_app_data_but_preserves_media_folder_by_default(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            env = self.make_env(root)
            local = Path(env["LOCALAPPDATA"])
            data = local / "ChatGPT" / "MediaDownloader"
            output = data / "my-exports" / "music"
            output.mkdir(parents=True)
            keep = output / "keep.mp3"
            keep.write_bytes(b"personal media")
            (data / "logs").mkdir()
            (data / "logs" / "app.log").write_text("log", encoding="utf-8")
            config = data / "config"
            config.mkdir()
            (config / "config.json").write_text(json.dumps({
                "music_dir": str(output),
                "video_dir": str(output.parent / "videos")
            }), encoding="utf-8")

            plan = discover_targets(env)
            self.assertTrue(any(item.path == output for item in plan.output_dirs))
            log = perform_cleanup(plan, env=env)
            self.assertTrue(keep.is_file())
            self.assertFalse((data / "logs" / "app.log").exists())
            self.assertTrue(any("PRESERVADO" in line for line in log))

    def test_cleanup_can_remove_media_only_when_explicitly_requested(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            env = self.make_env(root)
            local = Path(env["LOCALAPPDATA"])
            data = local / "ChatGPT" / "MediaDownloader"
            output = Path(env["USERPROFILE"]) / "OneDrive" / "media" / "music"
            output.mkdir(parents=True)
            (output / "song.mp3").write_bytes(b"demo")
            data.mkdir(parents=True)
            (data / "config").mkdir()
            (data / "config" / "config.json").write_text(json.dumps({
                "music_dir": str(output), "video_dir": ""
            }), encoding="utf-8")
            plan = discover_targets(env)
            self.assertTrue(any(item.path == output and item.safe_to_remove for item in plan.output_dirs))
            perform_cleanup(plan, remove_media=True, env=env)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()

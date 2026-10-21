import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import config


class ConfigTests(unittest.TestCase):
    def test_update_preferences_default_to_stable_and_require_confirmation(self):
        self.assertIs(config.DEFAULT_CONFIG["update_open_after"], True)
        self.assertIs(config.DEFAULT_CONFIG["update_check_on_startup"], True)
        self.assertIs(config.DEFAULT_CONFIG["update_include_prereleases"], False)

    def test_defaults_and_install_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            with patch.object(config, "APP_DATA", base), \
                 patch.object(config, "TOOLS_DIR", base / "tools"), \
                 patch.object(config, "TEMP_DIR", base / "temp"), \
                 patch.object(config, "LOG_DIR", base / "logs"), \
                 patch.object(config, "CONFIG_PATH", base / "config" / "config.json"), \
                 patch.object(config, "INSTALL_ID_PATH", base / "install_id.txt"):
                value = config.ensure_install_id()
                self.assertTrue(value)
                self.assertEqual(value, config.ensure_install_id())
                config.save_config(config.DEFAULT_CONFIG)
                loaded = config.load_config()
                self.assertEqual(loaded["auto_video_quality"], 1080)
                self.assertEqual(loaded["audio_bitrate"], 192)
                self.assertEqual(loaded["accent_color"], "#8B5CF6")
                self.assertFalse(loaded["animations_enabled"])


    def test_theme_accent_and_density_are_validated_and_persisted(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            with patch.object(config, "APP_DATA", base), \
                 patch.object(config, "TOOLS_DIR", base / "tools"), \
                 patch.object(config, "TEMP_DIR", base / "temp"), \
                 patch.object(config, "LOG_DIR", base / "logs"), \
                 patch.object(config, "CONFIG_PATH", base / "config" / "config.json"):
                chosen = dict(config.DEFAULT_CONFIG)
                chosen.update({"theme": "oled", "accent_color": "#12aBcD", "ui_density": "compact"})
                config.save_config(chosen)
                loaded = config.load_config()
                self.assertEqual(loaded["theme"], "oled")
                self.assertEqual(loaded["accent_color"], "#12ABCD")
                self.assertEqual(loaded["ui_density"], "compact")

                chosen.update({"theme": "ultraviolet", "accent_color": "purple", "ui_density": "ultra"})
                config.save_config(chosen)
                loaded = config.load_config()
                self.assertEqual(loaded["theme"], "dark")
                self.assertEqual(loaded["accent_color"], "#8B5CF6")
                self.assertEqual(loaded["ui_density"], "comfortable")


    def test_legacy_default_accent_is_migrated_but_custom_accent_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            with patch.object(config, "APP_DATA", base), \
                 patch.object(config, "TOOLS_DIR", base / "tools"), \
                 patch.object(config, "TEMP_DIR", base / "temp"), \
                 patch.object(config, "LOG_DIR", base / "logs"), \
                 patch.object(config, "CONFIG_PATH", base / "config" / "config.json"):
                config.CONFIG_PATH.parent.mkdir(parents=True)
                config.CONFIG_PATH.write_text(json.dumps({
                    "theme": "dark", "accent_color": "#2563EB",
                    "settings_schema_version": 2,
                    "animations_enabled": True
                }), encoding="utf-8")
                migrated = config.load_config()
                self.assertEqual(migrated["accent_color"], "#8B5CF6")
                self.assertEqual(migrated["settings_schema_version"], 5)
                self.assertTrue(migrated["animations_enabled"])

                config.CONFIG_PATH.write_text(json.dumps({
                    "theme": "dark", "accent_color": "#12ABCD",
                    "settings_schema_version": 1
                }), encoding="utf-8")
                custom = config.load_config()
                self.assertEqual(custom["accent_color"], "#12ABCD")


    def test_prerelease_preference_is_validated_and_persisted(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            with patch.object(config, "APP_DATA", base), \
                 patch.object(config, "TOOLS_DIR", base / "tools"), \
                 patch.object(config, "TEMP_DIR", base / "temp"), \
                 patch.object(config, "LOG_DIR", base / "logs"), \
                 patch.object(config, "CONFIG_PATH", base / "config" / "config.json"):
                chosen = dict(config.DEFAULT_CONFIG)
                chosen["update_include_prereleases"] = True
                config.save_config(chosen)
                loaded = config.load_config()
                self.assertIs(loaded["update_include_prereleases"], True)
                self.assertEqual(loaded["settings_schema_version"], 5)

                loaded["update_include_prereleases"] = "not-a-boolean"
                config.save_config(loaded)
                normalized = config.load_config()
                self.assertIs(normalized["update_include_prereleases"], False)

    def test_startup_repair_marker_persists_until_gui_confirms_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            marker = base / "temp" / "startup-repair-pending.json"
            with patch.object(config, "APP_DATA", base), patch.object(config, "TOOLS_DIR", base / "tools"), patch.object(config, "TEMP_DIR", base / "temp"), patch.object(config, "LOG_DIR", base / "logs"), patch.object(config, "CONFIG_PATH", base / "config" / "config.json"), patch.object(config, "STARTUP_REPAIR_PENDING_PATH", marker):
                config.mark_startup_repair_pending("5.1.1")
                self.assertTrue(config.startup_repair_is_pending())
                self.assertEqual(json.loads(marker.read_text(encoding="utf-8"))["version"], "5.1.1")
                self.assertTrue(config.clear_startup_repair_pending())
                self.assertFalse(config.startup_repair_is_pending())

if __name__ == "__main__":
    unittest.main()

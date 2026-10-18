import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import config


class ConfigTests(unittest.TestCase):
    def test_update_preferences_are_enabled_by_default(self):
        self.assertIs(config.DEFAULT_CONFIG["update_open_after"], True)
        self.assertIs(config.DEFAULT_CONFIG["update_check_on_startup"], True)

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


if __name__ == "__main__":
    unittest.main()

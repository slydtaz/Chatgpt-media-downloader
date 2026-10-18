import os
import unittest
from unittest.mock import patch

from app.platform import detect_system


class PlatformTests(unittest.TestCase):
    def test_detect_returns_known_shape(self):
        info = detect_system()
        self.assertTrue(info.os_name)
        self.assertTrue(info.architecture)
        self.assertIn(info.python_bits, (32, 64))

    def test_windows_host_arch_uses_w6432(self):
        with patch("app.platform._platform.system", return_value="Windows"), \
             patch("app.platform._platform.machine", return_value="AMD64"), \
             patch.dict(os.environ, {"PROCESSOR_ARCHITECTURE": "x86", "PROCESSOR_ARCHITEW6432": "AMD64"}, clear=False):
            info = detect_system()
            self.assertEqual(info.architecture, "x64")


if __name__ == "__main__":
    unittest.main()

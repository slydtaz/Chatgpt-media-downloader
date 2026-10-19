from __future__ import annotations

import unittest

from app.gui import MediaDownloaderApp


class PlaylistStrategyLabelTests(unittest.TestCase):
    def test_strategy_label_can_be_called_through_instance_style(self):
        # The startup bug came from this helper being defined without self while
        # called as self._strategy_label(...); staticmethod keeps the call valid.
        formatter = MediaDownloaderApp._strategy_label
        self.assertEqual(formatter("sequential"), "Um por vez (recomendado)")
        self.assertEqual(formatter("parallel"), "Paralelo (mais rápido)")
        self.assertEqual(formatter("unknown"), "Um por vez (recomendado)")


if __name__ == "__main__":
    unittest.main()

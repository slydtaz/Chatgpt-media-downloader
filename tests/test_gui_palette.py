import re
import unittest
from pathlib import Path

from app.gui import PALETTES


class GuiPaletteTests(unittest.TestCase):
    def test_all_referenced_color_keys_exist_in_every_theme(self):
        source = (Path(__file__).resolve().parents[1] / "app" / "gui.py").read_text(encoding="utf-8")
        referenced = set(re.findall(r'self\.colors\["([a-zA-Z0-9_]+)"\]', source))
        for theme, palette in PALETTES.items():
            with self.subTest(theme=theme):
                self.assertFalse(referenced - set(palette.keys()), referenced - set(palette.keys()))


if __name__ == "__main__":
    unittest.main()

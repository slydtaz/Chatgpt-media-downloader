import re
import unittest
from pathlib import Path

from app.gui import PALETTES, _contrast_text


class GuiPaletteTests(unittest.TestCase):
    def test_custom_accent_uses_the_higher_contrast_foreground(self):
        # Mid-tone gray has better contrast with dark text than with white text.
        # These cases cover both sides of the contrast crossover and its extremes.
        cases = {
            "#808080": "#11131A",
            "#2563EB": "#FFFFFF",
            "#FDE047": "#11131A",
            "#000000": "#FFFFFF",
            "#FFFFFF": "#11131A",
        }
        for accent, expected in cases.items():
            with self.subTest(accent=accent):
                self.assertEqual(_contrast_text(accent), expected)

    def test_all_referenced_color_keys_exist_in_every_theme(self):
        source = (Path(__file__).resolve().parents[1] / "app" / "gui.py").read_text(encoding="utf-8")
        referenced = set(re.findall(r'self\.colors\["([a-zA-Z0-9_]+)"\]', source))
        for theme, palette in PALETTES.items():
            with self.subTest(theme=theme):
                self.assertFalse(referenced - set(palette.keys()), referenced - set(palette.keys()))


if __name__ == "__main__":
    unittest.main()

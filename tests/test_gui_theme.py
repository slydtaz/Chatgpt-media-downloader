import unittest

from app.gui import (
    PALETTES,
    MediaDownloaderApp,
    _blend_hex,
    _contrast_text,
    _valid_hex_color,
    _rounded_polygon,
)


class GuiThemeTests(unittest.TestCase):
    def test_dark_light_and_oled_palettes_are_available(self):
        self.assertEqual(set(PALETTES), {"dark", "light", "oled"})
        required = {"bg", "panel", "panel2", "field", "fg", "muted", "border", "accent", "accent2", "accent_fg"}
        for palette in PALETTES.values():
            self.assertTrue(required.issubset(palette))

    def test_space_palette_exposes_violet_blue_and_pink_accents(self):
        for name in ("dark", "oled"):
            self.assertIn("space", PALETTES[name])
            self.assertIn("pink", PALETTES[name])
        points = _rounded_polygon(0, 0, 100, 48, 14)
        self.assertEqual(len(points) % 2, 0)
        self.assertGreaterEqual(len(points), 24)

    def test_custom_accent_color_validation_and_contrast(self):
        self.assertTrue(_valid_hex_color("#8B5CF6"))
        self.assertTrue(_valid_hex_color("#aBcD01"))
        self.assertFalse(_valid_hex_color("purple"))
        self.assertFalse(_valid_hex_color("#12345"))
        self.assertEqual(_contrast_text("#FFFFFF"), "#11131A")
        self.assertEqual(_contrast_text("#000000"), "#FFFFFF")

    def test_palette_blending_produces_valid_hex_color(self):
        self.assertEqual(_blend_hex("#000000", "#FFFFFF", 0.5), "#808080")
        self.assertTrue(_valid_hex_color(_blend_hex("#3B82F6", "#FFFFFF", 0.18)))

    def test_theme_and_density_labels_round_trip(self):
        self.assertEqual(MediaDownloaderApp._display_setting_value("theme", "oled"), "Preto OLED")
        self.assertEqual(MediaDownloaderApp._stored_setting_value("theme", "Preto OLED"), "oled")
        self.assertEqual(MediaDownloaderApp._display_setting_value("ui_density", "compact"), "Compacto")
        self.assertEqual(MediaDownloaderApp._stored_setting_value("ui_density", "Compacto"), "compact")


if __name__ == "__main__":
    unittest.main()

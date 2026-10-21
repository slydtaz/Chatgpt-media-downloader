import unittest

from app import visual_effects


class VisualEffectsTests(unittest.TestCase):
    def test_palette_lookup_is_known_and_has_valid_hex_colors(self):
        self.assertEqual(
            set(visual_effects.PALETTES),
            {"cosmic", "nebula", "aurora", "ocean"},
        )
        for name in visual_effects.PALETTES:
            colors = visual_effects.palette_colors(name)
            with self.subTest(name=name):
                self.assertGreaterEqual(len(colors), 4)
                self.assertTrue(all(len(color) == 7 and color.startswith("#") for color in colors))
        self.assertEqual(
            visual_effects.palette_colors("unknown"),
            visual_effects.palette_colors("cosmic"),
        )

    def test_strength_is_clamped_and_bad_values_are_safe(self):
        self.assertEqual(visual_effects._clamp_strength(-1), 0.0)
        self.assertEqual(visual_effects._clamp_strength(2), 1.0)
        self.assertEqual(visual_effects._clamp_strength("bad"), 0.55)

    @unittest.skipIf(visual_effects.Image is None, "Pillow is an optional runtime dependency")
    def test_static_gradient_preview_is_rgb_with_requested_size(self):
        image = visual_effects.render_gradient_preview(360, 90, "cosmic", 0.55)
        self.assertIsNotNone(image)
        self.assertEqual(image.size, (360, 90))
        self.assertEqual(image.mode, "RGB")

    @unittest.skipIf(visual_effects.Image is None, "Pillow is an optional runtime dependency")
    def test_atom_art_is_static_deterministic_and_respects_dimensions(self):
        first = visual_effects.render_atom_art(
            280, 190, palette="nebula", strength=0.55, orbit_count=3
        )
        second = visual_effects.render_atom_art(
            280, 190, palette="nebula", strength=0.55, orbit_count=3
        )
        self.assertEqual(first.size, (280, 190))
        self.assertEqual(first.mode, "RGBA")
        self.assertEqual(first.tobytes(), second.tobytes())

    @unittest.skipIf(visual_effects.Image is None, "Pillow is an optional runtime dependency")
    def test_disabling_glow_keeps_a_dark_static_canvas(self):
        image = visual_effects.render_ambient_gradient(120, 60, strength=0.0)
        self.assertEqual(image.size, (120, 60))
        self.assertEqual(image.getpixel((60, 30)), (5, 5, 16, 255))


if __name__ == "__main__":
    unittest.main()

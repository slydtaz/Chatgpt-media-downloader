import unittest

from app import ui_rendering


class AntialiasedRenderingTests(unittest.TestCase):
    @unittest.skipIf(ui_rendering.Image is None, "Pillow is optional for source installs")
    def test_panel_is_correct_size_and_keeps_backdrop_in_rounded_corner(self):
        image = ui_rendering.render_rounded_panel(
            180, 54,
            backdrop="#050617",
            surface="#10142C",
            border="#8B5CF6",
            radius=15,
            border_width=1,
        )
        self.assertEqual(image.size, (180, 54))
        self.assertEqual(image.mode, "RGB")
        self.assertEqual(image.getpixel((0, 0)), (5, 6, 23))
        self.assertEqual(image.getpixel((90, 27)), (16, 20, 44))

    @unittest.skipIf(ui_rendering.Image is None, "Pillow is optional for source installs")
    def test_button_has_transparent_round_corners_and_opaque_center(self):
        image = ui_rendering.render_rounded_button(
            190, 40,
            backdrop="#050617",
            edge="#8B5CF6",
            top="#743BEB",
            bottom="#4F46E5",
            outer_palette=("#743BEB", "#1687F8", "#21B6EB"),
            inner_palette=("#B52CE3", "#A78BFA", "#21B6EB"),
        )
        self.assertEqual(image.size, (190, 40))
        self.assertEqual(image.mode, "RGBA")
        self.assertEqual(image.getpixel((0, 0))[3], 0)
        self.assertEqual(image.getpixel((95, 20))[3], 255)

    @unittest.skipIf(ui_rendering.Image is None, "Pillow is optional for source installs")
    def test_hover_changes_fill_without_changing_dimensions(self):
        normal = ui_rendering.render_rounded_button(
            160, 38, backdrop="#050617", edge="#8B5CF6",
            top="#211C3A", bottom="#211C3A",
            outer_palette=("#743BEB", "#1687F8", "#21B6EB"),
            inner_palette=("#B52CE3", "#A78BFA", "#21B6EB"),
        )
        hover = ui_rendering.render_rounded_button(
            160, 38, backdrop="#050617", edge="#8B5CF6",
            top="#30234F", bottom="#30234F",
            outer_palette=("#743BEB", "#1687F8", "#21B6EB"),
            inner_palette=("#B52CE3", "#A78BFA", "#21B6EB"),
            hover_palette=("#743BEB", "#1687F8", "#21B6EB"),
            hover=True,
        )
        self.assertEqual(normal.size, hover.size)
        self.assertNotEqual(normal.tobytes(), hover.tobytes())


if __name__ == "__main__":
    unittest.main()

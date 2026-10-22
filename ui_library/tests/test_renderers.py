from pathlib import Path
import sys, unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import reusable_neon_ui as ui
from reusable_neon_ui import pillow_effects

class RendererTests(unittest.TestCase):
    def test_renderers_are_importable(self):
        self.assertTrue(callable(ui.render_ambient_gradient))
        self.assertTrue(callable(ui.render_gradient_preview))
        self.assertTrue(callable(ui.render_atom_art))
        self.assertTrue(callable(ui.render_rounded_panel))
        self.assertTrue(callable(ui.render_rounded_button))
    @unittest.skipIf(pillow_effects.Image is None, "Pillow is optional")
    def test_preview_size(self):
        image=ui.render_gradient_preview(160,64,"cosmic",.6)
        self.assertIsNotNone(image)
        self.assertEqual(image.size,(160,64))

if __name__=="__main__": unittest.main()

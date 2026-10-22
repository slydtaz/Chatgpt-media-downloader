from pathlib import Path
import sys, unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from reusable_neon_ui import GradientConfig, effect_names, register_effect, sample_gradient, unregister_effect
from reusable_neon_ui.effects import PALETTES, palette_colors

class EffectsTests(unittest.TestCase):
    def test_presets_have_hex_colors(self):
        self.assertIn("cosmic",PALETTES); self.assertIn("sunset",PALETTES)
        for colors in PALETTES.values():
            self.assertGreaterEqual(len(colors),2)
            self.assertTrue(all(len(c)==7 and c.startswith("#") for c in colors))
    def test_gradient_positions_differ(self):
        cfg=GradientConfig(colors=("#FF0000","#0000FF"),intensity=1,pulse_strength=0)
        self.assertNotEqual(sample_gradient(cfg,.05,.5,0),sample_gradient(cfg,.95,.5,0))
    def test_phase_changes_output(self):
        cfg=GradientConfig(colors=("#FF0000","#0000FF"),intensity=1,pulse_strength=0,speed=1)
        self.assertNotEqual(sample_gradient(cfg,.25,.5,0),sample_gradient(cfg,.25,.5,2))
    def test_trusted_effect_registration(self):
        register_effect("test_magenta",lambda config,x,y,phase:"#FF00CC")
        try:
            cfg=GradientConfig()
            cfg.mode="test_magenta"
            self.assertEqual(sample_gradient(cfg,.5,.5,0),"#FF00CC")
            self.assertIn("test_magenta",effect_names())
        finally: unregister_effect("test_magenta")
    def test_custom_palette_falls_back(self):
        self.assertEqual(palette_colors("unknown"),PALETTES["cosmic"])

if __name__=="__main__": unittest.main()

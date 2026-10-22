from pathlib import Path
import os, sys, tempfile, unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from reusable_neon_ui import BorderConfig, GradientConfig, UIConfig, load_config, save_config

class ConfigTests(unittest.TestCase):
    def test_defaults(self):
        cfg=UIConfig()
        self.assertEqual(cfg.schema,1)
        self.assertEqual(cfg.background.gradient.mode,"diagonal")
        self.assertTrue(cfg.button.border.enabled)
    def test_invalid_values_are_clamped(self):
        cfg=GradientConfig(mode="../bad",colors=("#GGGGGG",),intensity=99,
                           brightness_min=.9,brightness_max=.1,bubble_count=100,bubble_size=-1,speed=float("nan"))
        self.assertEqual(cfg.mode,"diagonal")
        self.assertGreaterEqual(cfg.intensity,0); self.assertLessEqual(cfg.intensity,1)
        self.assertGreaterEqual(cfg.brightness_max,cfg.brightness_min)
        self.assertLessEqual(cfg.bubble_count,20); self.assertGreaterEqual(cfg.bubble_size,.05)
        self.assertTrue(all(len(c)==7 for c in cfg.colors))
    def test_round_trip(self):
        cfg=UIConfig(reduced_motion=True)
        cfg.tab.gradient.mode="bubbles"; cfg.tab.gradient.bubble_count=12
        cfg.background.border=BorderConfig(glow=8,thickness=3)
        restored=UIConfig.from_dict(cfg.to_dict())
        self.assertTrue(restored.reduced_motion)
        self.assertEqual(restored.tab.gradient.mode,"bubbles")
        self.assertEqual(restored.tab.gradient.bubble_count,12)
        self.assertEqual(restored.background.border.glow,8)
    def test_atomic_save_load(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"settings.json"
            save_config(path,UIConfig(reduced_motion=True))
            self.assertTrue(load_config(path).reduced_motion)
            self.assertFalse(list(Path(folder).glob(".neon-ui-*.tmp")))
    def test_symlink_destination_is_rejected(self):
        if not hasattr(os,"symlink"): self.skipTest("symlink unsupported")
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); target=root/"real.json"; target.write_text("{}",encoding="utf-8")
            link=root/"link.json"
            try: link.symlink_to(target)
            except OSError: self.skipTest("symlink creation requires privileges")
            with self.assertRaises(ValueError): save_config(link,UIConfig())
    def test_bad_json_is_not_reset(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"broken.json"; path.write_text("{",encoding="utf-8")
            with self.assertRaises(ValueError): load_config(path)

if __name__=="__main__": unittest.main()

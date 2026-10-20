from __future__ import annotations

import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import ui_debug


def make_update_archive(files: dict[str, bytes | str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return buffer.getvalue()


class VersionAndGeometryTests(unittest.TestCase):
    def test_dev_versions_compare_numerically(self):
        self.assertGreater(ui_debug.version_key("0.1.0-dev.10"), ui_debug.version_key("0.1.0-dev.2"))
        self.assertGreater(ui_debug.version_key("0.1.1-dev.1"), ui_debug.version_key("0.1.0-dev.99"))
        self.assertGreater(ui_debug.version_key("0.1.0"), ui_debug.version_key("0.1.0-dev.99"))
        self.assertGreater(ui_debug.version_key("0.2.0-dev.1"), ui_debug.version_key("0.1.9"))

    def test_rounded_rectangle_points_stay_inside_requested_bounds(self):
        points = ui_debug.rounded_points(2, 3, 202, 63, 16)
        self.assertEqual(len(points) % 2, 0)
        xs, ys = points[0::2], points[1::2]
        self.assertGreaterEqual(min(xs), 2)
        self.assertLessEqual(max(xs), 202)
        self.assertGreaterEqual(min(ys), 3)
        self.assertLessEqual(max(ys), 63)

    def test_preview_url_validation_rejects_local_or_unsafe_targets(self):
        valid = "https://www.youtube.com/watch?v=aqz-KE-bpKQ"
        self.assertEqual(ui_debug.validate_preview_url(valid), valid)
        for invalid in (
            "file:///C:/private/video.mp4",
            "https://localhost/video",
            "http://127.0.0.1/video",
            "http://192.168.0.10/media",
            "https://user:password@youtube.com/watch?v=abc",
            "https://server.local/media",
            "https://youtube.com:8443/watch?v=abc",
        ):
            with self.subTest(url=invalid):
                with self.assertRaises(ValueError):
                    ui_debug.validate_preview_url(invalid)

    def test_media_duration_formatter(self):
        self.assertEqual(ui_debug.format_media_duration(90), "01:30")
        self.assertEqual(ui_debug.format_media_duration(3671), "1:01:11")
        self.assertEqual(ui_debug.format_media_duration(None), "Duração desconhecida")

    def test_adaptive_scale_supports_1440p_and_small_displays(self):
        self.assertEqual(ui_debug.adaptive_ui_scale(2560, 1440), 1.25)
        self.assertEqual(ui_debug.adaptive_ui_scale(1920, 1080), 1.0)
        self.assertEqual(ui_debug.adaptive_ui_scale(1366, 768), 0.82)
        self.assertEqual(ui_debug.adaptive_ui_scale(0, 0), 1.0)

    def test_splash_trails_use_reusable_smooth_lines(self):
        source = (ROOT / "ui_debug.py").read_text(encoding="utf-8")
        self.assertIn('"trail_glow"', source)
        self.assertIn('self.canvas.itemconfigure(particle["trail"], state=tk.HIDDEN)', source)
        self.assertIn("smooth=True, splinesteps=16", source)
        self.assertNotIn('for _ in range(9)]', source)

    def test_updater_url_allowlist_requires_https_and_official_hosts(self):
        self.assertTrue(ui_debug.validate_update_url("https://raw.githubusercontent.com/owner/repo/ui-debug/version.json"))
        self.assertTrue(ui_debug.validate_update_url("https://github.com/owner/repo/archive/refs/heads/ui-debug.zip"))
        for bad in (
            "http://github.com/owner/repo/file.zip",
            "https://github.com.attacker.example/owner/repo.zip",
            "https://user:pass@github.com/owner/repo.zip",
            "https://github.com:444/owner/repo.zip",
            "https://attacker.example/file.zip",
        ):
            with self.subTest(url=bad):
                self.assertFalse(ui_debug.validate_update_url(bad))

    def test_settings_path_is_separate_from_production_app_data(self):
        prototype = object.__new__(ui_debug.SpaceUIPrototype)
        path = prototype._settings_path()
        self.assertEqual(path.parent.name, "MediaDownloader-UI-debug")
        self.assertNotEqual(path.parent.name.casefold(), "mediadownloader")


class VisualConceptTests(unittest.TestCase):
    def test_action_icons_use_native_canvas_shapes(self):
        class FakeCanvas:
            def __init__(self):
                self.calls = []
            def _add(self, kind, args, kwargs):
                self.calls.append((kind, args, kwargs))
                return len(self.calls)
            def create_line(self, *args, **kwargs):
                return self._add("line", args, kwargs)
            def create_oval(self, *args, **kwargs):
                return self._add("oval", args, kwargs)
            def create_polygon(self, *args, **kwargs):
                return self._add("polygon", args, kwargs)
            def create_arc(self, *args, **kwargs):
                return self._add("arc", args, kwargs)

        for key in ("preview", "download", "convert", "settings", "save", "refresh", "playlist", "search"):
            with self.subTest(key=key):
                canvas = FakeCanvas()
                items = ui_debug.draw_action_icon(canvas, 20, 20, key, "#FFFFFF")
                self.assertTrue(items)
                self.assertEqual(len(items), len(canvas.calls))
                self.assertTrue(all(kind in {"line", "outline", "filled"} for _item, kind in items))

    def test_violet_blue_default_preset_and_soft_glow(self):
        self.assertEqual(ui_debug.DEFAULT_SETTINGS["accent_color"], "#895CFA")
        self.assertEqual(ui_debug.DEFAULT_SETTINGS["accent_color_2"], "#558FF4")
        self.assertEqual(ui_debug.PALETTES["dark"]["accent2"], "#6EA2FA")
        source = (ROOT / "ui_debug.py").read_text(encoding="utf-8")
        self.assertIn("self._glow_ids = []", source)
        self.assertIn('tags=("button-shape","button-glow")', source)
        self.assertIn('blend_hex(SPLASH_BACKGROUND, tint, .012 + .16*t**1.65)', source)
        self.assertIn('blend_hex(SPLASH_BACKGROUND, color, .31)', source)
        self.assertNotIn('("#F472B6", "#A78BFA")', source)

    def test_splash_has_coordinated_gradient_pairs_and_status_sequences(self):
        self.assertGreaterEqual(len(ui_debug.SPLASH_PALETTES), 6)
        for first, second in ui_debug.SPLASH_PALETTES:
            with self.subTest(first=first, second=second):
                self.assertRegex(first, r"^#[0-9A-Fa-f]{6}$")
                self.assertRegex(second, r"^#[0-9A-Fa-f]{6}$")
                self.assertNotEqual(first.lower(), second.lower())
        self.assertGreaterEqual(len(ui_debug.STARTUP_MESSAGES), 6)
        self.assertGreaterEqual(len(ui_debug.UPDATE_MESSAGES), 6)
        self.assertIn("órbitas", " ".join(ui_debug.STARTUP_MESSAGES).lower())

    def test_migrates_default_accent_pair_but_preserves_custom_color(self):
        prototype = object.__new__(ui_debug.SpaceUIPrototype)
        with tempfile.TemporaryDirectory() as directory:
            prototype.settings_path = Path(directory) / "settings.json"
            prototype.settings_path.write_text(json.dumps({
                "theme": "dark",
                "accent_color": "#7C5CFF",
                "accent_color_2": "#20D8E7"
            }), encoding="utf-8")
            migrated = prototype._load_settings()
            self.assertEqual(migrated["accent_color"], "#895CFA")
            self.assertEqual(migrated["accent_color_2"], "#558FF4")
            self.assertEqual(migrated["visual_preset_version"], 2)
            prototype.settings_path.write_text(json.dumps({
                "theme": "dark",
                "accent_color": "#AA33DD",
                "accent_color_2": "#33AADD"
            }), encoding="utf-8")
            custom = prototype._load_settings()
            self.assertEqual(custom["accent_color"], "#AA33DD")
            self.assertEqual(custom["accent_color_2"], "#33AADD")

    def test_prototype_has_independent_development_version(self):
        self.assertEqual(ui_debug.APP_VERSION, "0.1.0-dev.9")
        self.assertEqual(ui_debug.CHANNEL, "development")
        self.assertIn("ui-debug", ui_debug.UPDATE_BRANCH)
        self.assertNotIn("draw_orbit_icon", (ROOT / "ui_debug.py").read_text(encoding="utf-8"))
        source = (ROOT / "ui_debug.py").read_text(encoding="utf-8")
        self.assertIn("def draw_section_icon", source)
        self.assertIn("def adaptive_ui_scale", source)
        self.assertIn('self.backdrop.tk.call("lower", self.backdrop._w)', source)
        self.assertIn('self.nav_gap.pack(side="left", fill="y")', source)
        self.assertNotIn('self.root.geometry("1280x830")', source)
        self.assertIn("def preview_media_async", source)
        self.assertIn("def preview_playlist_async", source)
        self.assertIn("def _install_thumbnail", source)
        self.assertIn("def render_nav_icon_image", source)
        self.assertIn('resampling = getattr(Image, "Resampling", Image)', source)
        self.assertIn("extractor.extract_info(url, download=False)", source)
        self.assertIn('"skip_download": True', source)


class SelfUpdaterTests(unittest.TestCase):
    def version_manifest(self, version="0.1.1-dev.2"):
        return json.dumps({"version": version, "channel": "development"}).encode("utf-8")

    def test_update_replaces_only_its_own_allowlisted_files(self):
        archive_bytes = make_update_archive({
            "example-project/UI-debug/ui_debug.py": "UPDATED_UI_DEBUG = True\n",
            "example-project/UI-debug/version.json": self.version_manifest(),
            "example-project/app/gui.py": "DO_NOT_TOUCH = True\n",
            "example-project/UI-debug/random.exe": b"unrelated",
        })
        with tempfile.TemporaryDirectory() as directory:
            app_dir = Path(directory)
            (app_dir / "ui_debug.py").write_text("OLD_UI_DEBUG = True\n", encoding="utf-8")
            (app_dir / "version.json").write_text(self.version_manifest("0.1.0-dev.1").decode("utf-8"), encoding="utf-8")
            (app_dir / "preferences.json").write_text('{"keep": true}\n', encoding="utf-8")

            ui_debug.install_self_update(app_dir, archive_bytes)

            self.assertIn("UPDATED_UI_DEBUG", (app_dir / "ui_debug.py").read_text(encoding="utf-8"))
            self.assertIn("0.1.1-dev.2", (app_dir / "version.json").read_text(encoding="utf-8"))
            self.assertEqual((app_dir / "preferences.json").read_text(encoding="utf-8"), '{"keep": true}\n')
            self.assertFalse((app_dir / "gui.py").exists())
            self.assertFalse((app_dir / "random.exe").exists())

    def test_traversal_archive_is_rejected_and_existing_files_are_preserved(self):
        archive_bytes = make_update_archive({
            "example-project/UI-debug/ui_debug.py": "MALICIOUS_REPLACEMENT = True\n",
            "example-project/UI-debug/version.json": self.version_manifest(),
            "example-project/UI-debug/../outside.py": "BAD = True\n",
        })
        with tempfile.TemporaryDirectory() as directory:
            app_dir = Path(directory)
            (app_dir / "ui_debug.py").write_text("SAFE_OLD_FILE = True\n", encoding="utf-8")
            with self.assertRaises(RuntimeError):
                ui_debug.install_self_update(app_dir, archive_bytes)
            self.assertEqual((app_dir / "ui_debug.py").read_text(encoding="utf-8"), "SAFE_OLD_FILE = True\n")
            self.assertFalse((Path(directory).parent / "outside.py").exists())

    def test_duplicate_or_case_colliding_archive_paths_are_rejected(self):
        buffer = io.BytesIO()
        manifest = self.version_manifest()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("example-project/UI-debug/ui_debug.py", "first")
            archive.writestr("example-project/UI-debug/UI_DEBUG.py", "second")
            archive.writestr("example-project/UI-debug/version.json", manifest)
        with tempfile.TemporaryDirectory() as directory:
            app_dir = Path(directory)
            with self.assertRaises(RuntimeError):
                ui_debug.install_self_update(app_dir, buffer.getvalue())
            self.assertFalse((app_dir / "ui_debug.py").exists())

    def test_source_has_no_import_dependency_on_production_app_package(self):
        source = (ROOT / "ui_debug.py").read_text(encoding="utf-8")
        self.assertNotRegex(source, r"(?m)^\s*(?:from|import)\s+app(?:\.|\s|$)")
        self.assertIn("MediaDownloader-UI-debug", source)
        self.assertIn('UPDATE_BRANCH = "ui-debug"', source)


if __name__ == "__main__":
    unittest.main()

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PackagingTests(unittest.TestCase):
    def test_single_file_spec_is_windowed_and_uses_packaged_entry(self):
        spec = (ROOT / "ChatGPTMediaDownloader.spec").read_text(encoding="utf-8")
        self.assertIn("packaged_entry.py", spec)
        self.assertIn("console=False", spec)
        self.assertIn('name="ChatGPTMediaDownloader"', spec)
        self.assertIn("EXE(", spec)

    def test_windows_build_script_outputs_one_exe(self):
        script = (ROOT / "build_exe.bat").read_text(encoding="utf-8")
        self.assertIn("--clean ChatGPTMediaDownloader.spec", script)
        self.assertIn("dist\\ChatGPTMediaDownloader.exe", script)

    def test_github_workflow_targets_windows(self):
        workflow = (ROOT / ".github" / "workflows" / "build-windows.yml").read_text(encoding="utf-8")
        self.assertIn("runs-on: windows-latest", workflow)
        self.assertIn("dist/ChatGPTMediaDownloader.exe", workflow)


if __name__ == "__main__":
    unittest.main()

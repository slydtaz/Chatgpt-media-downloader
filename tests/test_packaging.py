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

    def test_build_script_generates_single_exe_and_checksum(self):
        script = (ROOT / "build_exe.bat").read_text(encoding="utf-8")
        self.assertIn("ChatGPTMediaDownloader.spec", script)
        self.assertIn("dist\\ChatGPTMediaDownloader.exe", script)
        self.assertIn("SHA256SUMS.txt", script)

    def test_github_workflow_targets_windows(self):
        workflow = (ROOT / ".github" / "workflows" / "build-windows.yml").read_text(encoding="utf-8")
        self.assertIn("runs-on: windows-latest", workflow)
        self.assertIn("dist/ChatGPTMediaDownloader.exe", workflow)

    def test_windows_unittest_steps_capture_native_stderr_and_unix_keeps_bash(self):
        matrix = (ROOT / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8")
        self.assertIn("if: runner.os == 'Windows'", matrix)
        self.assertIn("shell: cmd", matrix)
        self.assertIn("Compile source (Windows cmd)", matrix)
        self.assertIn("Run unit tests (Windows)", matrix)
        self.assertIn("run: ./tests/run_unittest_ci.ps1", matrix)
        self.assertIn("if: runner.os != 'Windows'", matrix)
        self.assertIn("shell: bash", matrix)
        self.assertIn("Compile source (Unix)", matrix)
        self.assertIn("Run unit tests (Unix)", matrix)
        self.assertNotIn("unittest discover -s tests -v 2>&1", matrix)

        for relative, step_name in [
            (".github/workflows/release.yml", "Run tests before packaging"),
            (".github/workflows/build-windows.yml", "Run tests"),
        ]:
            workflow = (ROOT / relative).read_text(encoding="utf-8")
            start = workflow.index(f"- name: {step_name}")
            block = workflow[start:start + 160]
            self.assertIn("shell: pwsh", block)
            self.assertIn("./tests/run_unittest_ci.ps1", block)
            self.assertNotIn("2>&1", block)

        runner = (ROOT / "tests" / "run_unittest_ci.ps1").read_text(encoding="utf-8")
        self.assertIn("Start-Process", runner)
        self.assertIn("RedirectStandardOutput = $stdoutPath", runner)
        self.assertIn("RedirectStandardError = $stderrPath", runner)
        self.assertIn("$process.ExitCode", runner)


    def test_versioned_release_title_and_hotfix_are_configured(self):
        workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
        self.assertIn('tag_name: ${{ env.RELEASE_TAG }}', workflow)
        self.assertIn('name: ${{ env.RELEASE_NAME }}', workflow)
        self.assertIn('$releaseName = "$version - stable"', workflow)
        self.assertIn('$releaseName = "$version - stable hotfix-$($env:HOTFIX_NUMBER)"', workflow)


if __name__ == "__main__":
    unittest.main()

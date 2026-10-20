import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PackagingTests(unittest.TestCase):
    def test_single_file_spec_is_windowed_and_uses_packaged_entry(self):
        spec = (ROOT / "ChatGPTMediaDownloader.spec").read_text(encoding="utf-8")
        self.assertIn("packaged_entry.py", spec)
        self.assertIn("console=False", spec)
        self.assertIn('name="ChatGPTMediaDownloader"', spec)
        self.assertIn('"PIL.ImageTk"', spec)
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

    def test_windows_unittest_runner_is_isolated_and_unix_keeps_bash(self):
        matrix = (ROOT / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8")
        self.assertIn("if: runner.os == 'Windows'", matrix)
        self.assertIn("shell: pwsh", matrix)
        self.assertIn("Run unit tests (Windows)", matrix)
        self.assertIn("run: ./tests/run_unittest_ci.ps1", matrix)
        self.assertIn("if: runner.os != 'Windows'", matrix)
        self.assertIn("shell: bash", matrix)
        self.assertIn("Run unit tests (Unix)", matrix)

        for relative, step_name in [
            (".github/workflows/release.yml", "Run tests before packaging"),
            (".github/workflows/build-windows.yml", "Run tests"),
        ]:
            workflow = (ROOT / relative).read_text(encoding="utf-8")
            start = workflow.index(f"- name: {step_name}")
            block = workflow[start:start + 180]
            self.assertIn("shell: pwsh", block)
            self.assertIn("./tests/run_unittest_ci.ps1", block)

        runner = (ROOT / "tests" / "run_unittest_ci.ps1").read_text(encoding="utf-8")
        self.assertIn("ProcessStartInfo", runner)
        self.assertIn("CreateNoWindow = $true", runner)
        self.assertIn("RedirectStandardOutput = $true", runner)
        self.assertIn("RedirectStandardError = $true", runner)
        self.assertIn("$process.ExitCode", runner)


    def test_application_version_metadata_is_consistent(self):
        import re

        config = (ROOT / "app" / "config.py").read_text(encoding="utf-8")
        metadata = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        build_script = (ROOT / "build_exe.bat").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        version = re.search(r'^VERSION\s*=\s*"([^"]+)"', config, re.MULTILINE).group(1)
        package_version = re.search(r'^version\s*=\s*"([^"]+)"', metadata, re.MULTILINE).group(1)
        self.assertEqual(version, package_version)
        self.assertIn(f"ChatGPT Media Downloader {version} - Build", build_script)
        badge_version = version.replace("-", "--")
        self.assertIn(f"vers%C3%A3o-fonte%20{badge_version}", readme)
        version_info = (ROOT / "windows_version_info.txt").read_text(encoding="utf-8")
        self.assertIn(f"StringStruct('FileVersion', '{version}')", version_info)
        self.assertIn(f"StringStruct('ProductVersion', '{version}')", version_info)
        spec = (ROOT / "ChatGPTMediaDownloader.spec").read_text(encoding="utf-8")
        version_tuple = ", ".join(version.split("-", 1)[0].split("."))
        self.assertIn(f"filevers=({version_tuple}, 0)", version_info)
        self.assertIn(f"prodvers=({version_tuple}, 0)", version_info)
        self.assertIn('version=str(ROOT / "windows_version_info.txt")', spec)
        self.assertIn("github.com/slydtaz/Chatgpt-media-downloader", version_info)
        self.assertIn("nao afiliado a OpenAI", version_info)

    def test_beta_release_scans_all_runtime_inputs_and_keeps_stable_gate_strict(self):
        workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
        scanner = (ROOT / "scripts" / "virus_total_scan.py").read_text(encoding="utf-8")
        stager = (ROOT / "scripts" / "stage_runtime_dependencies_for_scan.py").read_text(encoding="utf-8")
        self.assertIn("Stage runtime dependencies for VirusTotal review", workflow)
        self.assertIn("yt-dlp.exe", workflow)
        self.assertIn("ffmpeg.exe", workflow)
        self.assertIn("ffprobe.exe", workflow)
        self.assertIn("Security-Inventory.txt", workflow)
        self.assertIn("if ($isPrerelease)", workflow)
        self.assertIn("Stable release blocked", workflow)
        self.assertIn("VirusTotal public analysis report", scanner)
        self.assertIn("DETECTION:", scanner)
        self.assertIn("install_tool_from_release", stager)
        self.assertIn("_verify_checksum", (ROOT / "app" / "updater.py").read_text(encoding="utf-8"))

    def test_versioned_release_title_and_hotfix_are_configured(self):
        workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
        self.assertIn('tag_name: ${{ env.RELEASE_TAG }}', workflow)
        self.assertIn('name: ${{ env.RELEASE_NAME }}', workflow)
        self.assertIn("      - 'v*'", workflow)
        self.assertIn('git archive --format=zip', workflow)
        self.assertIn('$releaseName = "$version - stable"', workflow)
        self.assertIn("$commitSubject = git log -1 --format=%s", workflow)
        self.assertIn("$commitSubject -match", workflow)
        self.assertIn('$releaseName = "$version - stable (hotfix-$hotfixNumber)"', workflow)


if __name__ == "__main__":
    unittest.main()

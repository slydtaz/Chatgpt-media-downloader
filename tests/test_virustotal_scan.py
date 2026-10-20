from __future__ import annotations

import unittest

import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from scripts.virus_total_scan import (
    VirusTotalAPIError, _is_trusted_upload_host, submit_file, summarize_analysis,
)


class VirusTotalReportTests(unittest.TestCase):
    def test_detection_details_include_engine_and_signature_label(self):
        summary, detections, has_findings = summarize_analysis(
            "ChatGPTMediaDownloader.exe",
            {
                "stats": {"malicious": 1, "suspicious": 0, "undetected": 65, "harmless": 0},
                "results": {
                    "ExampleAV": {
                        "category": "malicious",
                        "result": "Trojan.Test.Heuristic",
                        "method": "blacklist",
                        "engine_version": "1.2.3",
                        "engine_update": "20261020",
                    },
                    "CleanAV": {"category": "undetected", "result": None},
                },
            },
        )
        self.assertIn("malicious=1", summary)
        self.assertTrue(has_findings)
        self.assertEqual(len(detections), 1)
        self.assertIn("engine=ExampleAV", detections[0])
        self.assertIn("result=Trojan.Test.Heuristic", detections[0])
        self.assertIn("engine_update=20261020", detections[0])

    def test_upload_host_policy_allows_only_official_hosts(self):
        self.assertTrue(_is_trusted_upload_host("www.virustotal.com"))
        self.assertTrue(_is_trusted_upload_host("api.virustotal.com"))
        self.assertTrue(_is_trusted_upload_host("storage.googleapis.com"))
        self.assertFalse(_is_trusted_upload_host("storage.googleapis.com.attacker.example"))
        self.assertFalse(_is_trusted_upload_host("attacker.example"))

    def test_http_409_reuses_existing_hash_report_instead_of_assuming_clean(self):
        attrs = {
            "last_analysis_stats": {"malicious": 0, "suspicious": 1, "undetected": 70},
            "last_analysis_results": {
                "ExampleAV": {"category": "suspicious", "result": "Generic.Test"}
            },
            "last_analysis_date": 1792490000,
        }
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "yt-dlp.exe"
            path.write_bytes(b"same upstream executable content")
            expected = hashlib.sha256(path.read_bytes()).hexdigest()
            with patch("scripts.virus_total_scan._api_json", side_effect=[
                VirusTotalAPIError(409, "already exists"),
                {"data": {"attributes": attrs}},
            ]) as request:
                analysis_id, existing = submit_file(path, "unit-test-key")
        self.assertIsNone(analysis_id)
        self.assertEqual(existing["status"], "completed")
        self.assertEqual(existing["stats"], attrs["last_analysis_stats"])
        self.assertEqual(existing["results"], attrs["last_analysis_results"])
        self.assertEqual(request.call_args_list[1].args[0], f"https://www.virustotal.com/api/v3/files/{expected}")

    def test_clean_result_is_not_misclassified_as_a_detection(self):
        summary, detections, has_findings = summarize_analysis(
            "yt-dlp.exe",
            {
                "stats": {"malicious": 0, "suspicious": 0, "undetected": 65},
                "results": {
                    "CleanAV": {"category": "undetected", "result": None},
                    "HarmlessAV": {"category": "harmless", "result": None},
                },
            },
        )
        self.assertIn("malicious=0", summary)
        self.assertEqual(detections, [])
        self.assertFalse(has_findings)


if __name__ == "__main__":
    unittest.main()

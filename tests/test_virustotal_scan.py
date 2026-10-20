from __future__ import annotations

import unittest

from scripts.virus_total_scan import summarize_analysis


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

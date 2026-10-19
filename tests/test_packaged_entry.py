from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import packaged_entry


class PackagedEntryTests(unittest.TestCase):
    def test_successful_bootstrap_is_logged(self):
        with tempfile.TemporaryDirectory() as td:
            log_path = Path(td) / "startup.log"
            with patch("packaged_entry._startup_log_paths", return_value=[log_path]):
                result = packaged_entry.main(lambda: None)

            self.assertEqual(result, 0)
            log = log_path.read_text(encoding="utf-8")
            self.assertIn("ENTRYPOINT: início do executável.", log)
            self.assertIn("módulo de inicialização carregado", log)
            self.assertIn("bootstrap retornou normalmente", log)

    def test_unhandled_bootstrap_error_is_logged_and_shown(self):
        def fail_startup():
            raise RuntimeError("simulated startup crash")

        with tempfile.TemporaryDirectory() as td:
            log_path = Path(td) / "startup.log"
            with patch("packaged_entry._startup_log_paths", return_value=[log_path]), patch(
                "packaged_entry._show_startup_error"
            ) as show_error:
                result = packaged_entry.main(fail_startup)

            self.assertEqual(result, 1)
            log = log_path.read_text(encoding="utf-8")
            self.assertIn("ERRO NÃO TRATADO", log)
            self.assertIn("RuntimeError: simulated startup crash", log)
            show_error.assert_called_once()
            self.assertIn("simulated startup crash", show_error.call_args.args[0])
            self.assertIn(str(log_path), show_error.call_args.args[0])

    def test_log_writer_falls_back_when_first_location_is_unwritable(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            blocking_file = root / "not-a-directory"
            blocking_file.write_text("block", encoding="utf-8")
            bad_path = blocking_file / "startup.log"
            fallback_path = root / "fallback" / "startup.log"

            with patch(
                "packaged_entry._startup_log_paths",
                return_value=[bad_path, fallback_path],
            ):
                written_path = packaged_entry._write_startup_log("fallback works")

            self.assertEqual(written_path, fallback_path)
            self.assertIn("fallback works", fallback_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

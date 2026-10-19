from __future__ import annotations

import logging
import unittest
from unittest.mock import Mock, patch

from app.gui import run


class FakeRoot:
    def __init__(self):
        self.calls = []
        self.report_callback_exception = None

    def _call(self, name, *args, **kwargs):
        self.calls.append((name, args, kwargs))

    def withdraw(self): self._call("withdraw")
    def deiconify(self): self._call("deiconify")
    def protocol(self, *args): self._call("protocol", *args)
    def update_idletasks(self): self._call("update_idletasks")
    def lift(self): self._call("lift")
    def focus_force(self): self._call("focus_force")
    def mainloop(self): self._call("mainloop")
    def destroy(self): self._call("destroy")
    def winfo_exists(self): return True


class GuiStartupTests(unittest.TestCase):
    def test_root_stays_hidden_and_is_destroyed_when_ui_construction_fails(self):
        root = FakeRoot()
        with patch("app.gui.tk.Tk", return_value=root), \
             patch("app.gui.MediaDownloaderApp", side_effect=RuntimeError("simulated widget construction failure")), \
             patch("app.logging_utils.setup_logging", return_value=logging.getLogger("gui-startup-test")):
            with self.assertRaisesRegex(RuntimeError, "simulated widget construction failure"):
                run()

        call_names = [entry[0] for entry in root.calls]
        self.assertLess(call_names.index("withdraw"), call_names.index("destroy"))
        self.assertNotIn("deiconify", call_names)
        self.assertNotIn("mainloop", call_names)
        self.assertGreaterEqual(call_names.count("destroy"), 1)

    def test_successful_ui_is_revealed_only_after_window_layout_is_ready(self):
        root = FakeRoot()
        app = Mock()
        app.logger = logging.getLogger("gui-startup-success-test")
        with patch("app.gui.tk.Tk", return_value=root), \
             patch("app.gui.MediaDownloaderApp", return_value=app), \
             patch("app.config.clear_startup_repair_pending", return_value=True):
            run()

        call_names = [entry[0] for entry in root.calls]
        self.assertLess(call_names.index("withdraw"), call_names.index("deiconify"))
        self.assertLess(call_names.index("update_idletasks"), call_names.index("deiconify"))
        self.assertIn("mainloop", call_names)
        self.assertIn("destroy", call_names)


if __name__ == "__main__":
    unittest.main()

import unittest

from app.process_utils import hidden_subprocess_kwargs, refresh_windows_shell_items


class HiddenSubprocessTests(unittest.TestCase):
    def test_non_windows_has_no_windows_flags(self):
        self.assertEqual(hidden_subprocess_kwargs("posix"), {})


    def test_shell_refresh_is_noop_on_non_windows(self):
        self.assertEqual(refresh_windows_shell_items(["anything.mp3"], platform_name="posix"), 0)

    def test_windows_uses_create_no_window_flag(self):
        kwargs = hidden_subprocess_kwargs("nt")
        self.assertEqual(kwargs.get("creationflags"), 0x08000000)


if __name__ == "__main__":
    unittest.main()

import unittest
from app.security import redact_sensitive, safe_filename_part, validate_url


class SecurityTests(unittest.TestCase):
    def test_validate_url(self):
        self.assertTrue(validate_url("https://example.com/video")[0])
        self.assertFalse(validate_url("ftp://example.com")[0])
        self.assertFalse(validate_url("not-a-url")[0])

    def test_redaction(self):
        value = redact_sensitive("https://example.com/file?token=SECRET&x=1")
        self.assertNotIn("SECRET", value)
        self.assertNotIn("token=SECRET", value)

    def test_filename(self):
        value = safe_filename_part('A<>:"/\\\\|?*B')
        self.assertNotRegex(value, r'[<>:"/\\\\|?*]')
        self.assertLessEqual(len(value.encode("utf-8")), 200)


if __name__ == "__main__":
    unittest.main()

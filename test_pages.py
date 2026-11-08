"""Every HTML page loads, uses the shared look, and links to the other pages."""

import unittest
from unittest.mock import patch

from app import app


class TestPages(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def get_page(self, path):
        r = self.client.get(path)
        self.assertEqual(r.status_code, 200, path)
        return r.get_data(as_text=True)

    def test_pages_use_shared_style_and_top_bar(self):
        with patch("app.current_user", return_value=object()):  # "/" needs a login
            for path in ["/", "/login", "/upload"]:
                html = self.get_page(path)
                self.assertIn("css/app.css", html, path)
                self.assertIn('href="/upload"', html, path)  # top bar links
                self.assertIn('href="/login"', html, path)

    def test_current_page_is_highlighted(self):
        html = self.get_page("/upload")
        self.assertIn('href="/upload" class="is-active"', html)
        self.assertIn('href="/login" class=""', html)

    def test_welcome_page_loads_without_login(self):
        html = self.get_page("/welcome")
        self.assertIn("css/styles.css", html)

    def test_stylesheets_are_served(self):
        for path in ["/static/css/app.css", "/static/css/styles.css"]:
            r = self.client.get(path)
            self.assertEqual(r.status_code, 200, path)
            r.close()  # free the open file (Windows warns otherwise)


if __name__ == "__main__":
    unittest.main()

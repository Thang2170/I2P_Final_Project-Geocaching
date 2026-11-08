"""Tests that the map page sends logged-out visitors to the login page."""

import unittest
from unittest.mock import patch

from app import app


class TestLoginRedirect(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_logged_out_visitor_goes_to_login(self):
        r = self.client.get("/")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login", r.headers["Location"])

    def test_redirect_remembers_drag_mode(self):
        # "next" must keep "?drag" so the user lands back in drag mode after login.
        r = self.client.get("/?drag")
        self.assertIn("next=/?drag", r.headers["Location"])

    def test_logged_in_user_sees_map(self):
        with patch("app.current_user", return_value=object()):
            r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b'href="/login"', r.data)  # the Account link is on the map

    def test_login_page_still_loads(self):
        self.assertEqual(self.client.get("/login").status_code, 200)


if __name__ == "__main__":
    unittest.main()

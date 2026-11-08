"""The map shows steps and calories, and the account page has a weight box."""

import unittest
from unittest.mock import patch

from app import create_app
from models import db


class TestWalkPages(unittest.TestCase):
    def setUp(self):
        self.app = create_app("sqlite:///:memory:")
        self.client = self.app.test_client()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()
            db.engine.dispose()

    def test_map_board_has_steps_and_calories(self):
        with patch("app.current_user", return_value=object()):  # "/" needs a login
            html = self.client.get("/").get_data(as_text=True)
        self.assertIn('id="boardSteps"', html)
        self.assertIn('id="boardCal"', html)
        self.assertIn("/api/walk-stats", html)

    def test_account_page_has_a_weight_form(self):
        html = self.client.get("/login").get_data(as_text=True)
        self.assertIn('id="weightForm"', html)

    def test_upload_page_sends_logged_out_visitors_to_login(self):
        html = self.client.get("/upload").get_data(as_text=True)
        self.assertIn("/login?next=/upload", html)

    def test_walk_stats_is_registered_in_the_real_app(self):
        r = self.client.get("/api/walk-stats?distance_m=750")
        self.assertEqual(r.get_json()["steps"], 1000)


if __name__ == "__main__":
    unittest.main()

"""The map and the account page show coins."""

import unittest
from unittest.mock import patch

from app import create_app
from models import db


class TestCoinPages(unittest.TestCase):
    def setUp(self):
        self.app = create_app("sqlite:///:memory:")
        self.client = self.app.test_client()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()
            db.engine.dispose()

    def test_map_has_a_coin_counter_and_claims_coins(self):
        with patch("app.current_user", return_value=object()):  # "/" needs a login
            html = self.client.get("/").get_data(as_text=True)
        self.assertIn('id="coinInfo"', html)
        self.assertIn("/claim", html)

    def test_account_page_shows_coins(self):
        html = self.client.get("/login").get_data(as_text=True)
        self.assertIn('id="coins"', html)

    def test_coin_routes_are_registered_in_the_real_app(self):
        self.assertEqual(self.client.get("/api/coins").status_code, 401)  # needs a login


if __name__ == "__main__":
    unittest.main()

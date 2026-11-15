"""The Hunts page uses the shared look, and the real app has the demo hunt."""

import unittest

from app import create_app
from models import db


class TestHuntPages(unittest.TestCase):
    def setUp(self):
        self.app = create_app("sqlite:///:memory:")
        self.client = self.app.test_client()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()
            db.engine.dispose()

    def test_hunts_page_uses_shared_style_and_is_highlighted(self):
        html = self.client.get("/hunts").get_data(as_text=True)
        self.assertIn("css/app.css", html)
        self.assertIn('href="/hunts" class="is-active"', html)

    def test_other_pages_link_to_hunts(self):
        for path in ["/upload", "/login", "/shop"]:
            with self.subTest(path=path):
                self.assertIn('href="/hunts"', self.client.get(path).get_data(as_text=True))

    def test_the_real_app_starts_with_a_demo_hunt(self):
        hunts = self.client.get("/api/hunts").get_json()
        self.assertEqual(len(hunts), 1)
        self.assertEqual((hunts[0]["name"], hunts[0]["capacity"], hunts[0]["playing"]), ("NTHU campus walk", 5, 0))


if __name__ == "__main__":
    unittest.main()

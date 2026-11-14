"""The welcome page (/welcome) after the map preview and How it works cards were removed."""

import unittest

from app import create_app
from models import db


class TestWelcomePage(unittest.TestCase):
    def setUp(self):
        self.app = create_app("sqlite:///:memory:")
        self.html = self.app.test_client().get("/welcome").get_data(as_text=True)

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()
            db.engine.dispose()

    def test_the_map_preview_card_is_gone(self):
        self.assertNotIn('class="map-panel"', self.html)
        self.assertNotIn("map-illustration", self.html)

    def test_the_how_it_works_card_is_gone(self):
        self.assertNotIn('id="how-it-works"', self.html)
        self.assertNotIn('href="#how-it-works"', self.html)  # no link to a missing section

    def test_the_sidebar_help_card_opens_the_tour(self):
        self.assertIn('href="/?tour"', self.html)

    def test_the_leaderboard_card_stays(self):
        self.assertIn('id="top-players"', self.html)


if __name__ == "__main__":
    unittest.main()

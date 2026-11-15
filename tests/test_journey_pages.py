"""The map page has the Start button and the live journey panel."""

import unittest
from unittest.mock import patch

from app import create_app
from models import db


class TestJourneyPage(unittest.TestCase):
    def setUp(self):
        self.app = create_app("sqlite:///:memory:")
        self.client = self.app.test_client()
        with patch("app.current_user", return_value=object()):  # "/" needs a login
            self.html = self.client.get("/").get_data(as_text=True)

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()
            db.engine.dispose()

    def test_treasure_board_has_a_start_button(self):
        self.assertIn('id="startBtn"', self.html)
        self.assertIn("Start journey", self.html)

    def test_panel_shows_the_live_numbers(self):
        for element in ("jTime", "jPace", "jDist", "jSteps", "jCal", "jTo"):
            with self.subTest(element=element):
                self.assertIn(f'id="{element}"', self.html)

    def test_panel_has_pause_and_finish(self):
        self.assertIn('id="jPause"', self.html)
        self.assertIn('id="jFinish"', self.html)

    def test_steps_and_calories_come_from_python(self):
        self.assertIn("/api/walk-stats?distance_m=", self.html)

    def test_arriving_saves_the_hunt_and_the_finish_button_does_not(self):
        self.assertIn('id="jSaved"', self.html)
        self.assertIn("/api/journeys", self.html)
        self.assertIn("finishJourney(true)", self.html)    # Python said you arrived
        self.assertIn("finishJourney(false)", self.html)   # the button only stops the clock

    def test_top_bar_links_to_the_community(self):
        self.assertIn('href="/community"', self.html)

    def test_css_styles_the_panel(self):
        css = self.client.get("/static/css/app.css").get_data(as_text=True)
        self.assertIn(".journey", css)
        self.assertIn("body.is-journey .sheet", css)


if __name__ == "__main__":
    unittest.main()

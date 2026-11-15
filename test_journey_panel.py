"""The journey panel is a low bar at the bottom of the map, so the route stays visible."""

import unittest
from unittest.mock import patch

from app import create_app
from models import db


class TestJourneyPanel(unittest.TestCase):
    def setUp(self):
        self.app = create_app("sqlite:///:memory:")
        client = self.app.test_client()
        with patch("app.current_user", return_value=object()):  # "/" needs a login
            self.html = client.get("/").get_data(as_text=True)
        self.css = client.get("/static/css/app.css").get_data(as_text=True)

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()
            db.engine.dispose()

    def test_it_sits_at_the_bottom(self):
        block = self.css[self.css.index(".journey {"):]
        block = block[:block.index("}")]
        self.assertIn("bottom: 12px", block)
        self.assertNotIn("top:", block)

    def test_it_can_be_folded(self):
        self.assertIn('id="jFold"', self.html)
        self.assertIn(".journey.is-folded", self.css)

    def test_the_route_is_fitted_above_the_panel(self):
        self.assertIn("!journeyBox.hidden ? journeyBox : statusCard()", self.html)
        self.assertIn("bottomBox.offsetHeight", self.html)
        self.assertIn("map.fitBounds(routeLine.getBounds(), routePadding())", self.html)


if __name__ == "__main__":
    unittest.main()

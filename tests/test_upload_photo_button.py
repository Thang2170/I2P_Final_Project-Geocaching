"""The photo picker's "Choose File" button uses the pixel theme."""

import unittest

from app import create_app
from models import db


class TestPhotoButton(unittest.TestCase):
    def setUp(self):
        self.app = create_app("sqlite:///:memory:")
        self.css = self.app.test_client().get("/static/css/app.css").get_data(as_text=True)

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()
            db.engine.dispose()

    def test_the_choose_file_button_is_styled(self):
        rule = self.css[self.css.index('input[type="file"]::file-selector-button {'):]
        rule = rule[:rule.index("}")]
        self.assertIn("font-family: var(--font-pixel)", rule)
        self.assertIn("border-radius: 0", rule)

    def test_it_reacts_to_hover_and_keyboard(self):
        self.assertIn('input[type="file"]::file-selector-button:hover', self.css)
        self.assertIn('input[type="file"]:focus-visible::file-selector-button', self.css)


if __name__ == "__main__":
    unittest.main()

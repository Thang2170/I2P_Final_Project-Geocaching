"""Your own Account page shows your full profile, the same view other players see."""

import unittest

from app import create_app
from models import db


class TestAccountPage(unittest.TestCase):
    def setUp(self):
        self.app = create_app("sqlite:///:memory:")
        self.client = self.app.test_client()
        self.login_html = self.client.get("/login").get_data(as_text=True)
        self.profile_html = self.client.get("/players/ann").get_data(as_text=True)

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()
            db.engine.dispose()

    def test_account_page_has_the_full_profile(self):
        for part in ('id="sCoins"', 'id="sHunts"', 'id="sSteps"', 'id="hunts"', 'id="hidden"', 'id="posts"',
                     "loadProfile(user.username)"):
            with self.subTest(part=part):
                self.assertIn(part, self.login_html)

    def test_both_pages_use_the_same_profile_view(self):
        for html in (self.login_html, self.profile_html):
            self.assertIn("async function loadProfile(username)", html)
        # the profile markup is the same on both pages
        piece = 'class="panel profile__head"'
        self.assertIn(piece, self.login_html)
        self.assertIn(piece, self.profile_html)

    def test_account_settings_are_still_there(self):
        for part in ('id="weightForm"', 'id="logout"', 'id="toMap"', 'href="/?tour"', 'id="coins"'):
            with self.subTest(part=part):
                self.assertIn(part, self.login_html)

    def test_logged_out_visitors_still_get_the_forms(self):
        for part in ('id="loginForm"', 'id="registerForm"', 'id="welcomeCard"'):
            with self.subTest(part=part):
                self.assertIn(part, self.login_html)

    def test_no_innerhtml(self):
        self.assertNotIn(".innerHTML", self.login_html)
        self.assertNotIn(".innerHTML", self.profile_html)


if __name__ == "__main__":
    unittest.main()

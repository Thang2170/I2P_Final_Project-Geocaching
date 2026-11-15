"""The Community page is laid out like a news feed and only uses safe text."""

import unittest

from app import create_app
from models import db


class TestFeedPage(unittest.TestCase):
    def setUp(self):
        self.app = create_app("sqlite:///:memory:")
        self.client = self.app.test_client()
        self.html = self.client.get("/community").get_data(as_text=True)

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()
            db.engine.dispose()

    def test_three_columns(self):
        for part in ("fb__left", "fb__main", "fb__right"):
            with self.subTest(part=part):
                self.assertIn(part, self.html)

    def test_has_a_composer_and_a_feed(self):
        for element in ('id="composer"', 'id="postText"', 'id="postBtn"', 'id="feed"', 'id="more"'):
            with self.subTest(element=element):
                self.assertIn(element, self.html)

    def test_talks_to_the_feed_api(self):
        for url in ("/api/feed?offset=", "/api/posts", "/like", "/comments", "/api/community", "/api/journeys/mine"):
            with self.subTest(url=url):
                self.assertIn(url, self.html)

    def test_never_uses_innerhtml(self):
        self.assertNotIn(".innerHTML", self.html)  # the comment may name it; the code must not use it

    def test_uses_the_shared_look(self):
        self.assertIn("css/app.css", self.html)
        self.assertIn('class="topbar"', self.html)

    def test_css_styles_the_feed(self):
        css = self.client.get("/static/css/app.css").get_data(as_text=True)
        for rule in (".fb ", ".post ", ".hunt-card", ".avatar--5", ".comment__bubble"):
            with self.subTest(rule=rule):
                self.assertIn(rule, css)

    def test_the_welcome_sidebar_links_to_the_community(self):
        html = self.client.get("/welcome").get_data(as_text=True)
        self.assertIn('class="side-nav__link" href="/community"', html)
        css = self.client.get("/static/css/pixel.css").get_data(as_text=True)
        self.assertIn(".px-icon--comment", css)


if __name__ == "__main__":
    unittest.main()

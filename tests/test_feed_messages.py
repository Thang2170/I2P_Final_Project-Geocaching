"""Errors about a post (an empty comment, a failed like) show under that post's comment box."""

import unittest

from app import create_app
from models import db


class TestPostMessages(unittest.TestCase):
    def setUp(self):
        self.app = create_app("sqlite:///:memory:")
        client = self.app.test_client()
        self.html = client.get("/community").get_data(as_text=True)
        self.css = client.get("/static/css/app.css").get_data(as_text=True)

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()
            db.engine.dispose()

    def test_each_post_has_its_own_message_line_after_the_comment_box(self):
        self.assertIn('el("p", "", "message post__message")', self.html)
        self.assertRegex(self.html, r"card\.append\(counts, [\w, ]*reply, postMsg\)")  # last, under the box

    def test_comment_and_like_errors_go_there(self):
        self.assertIn("} catch (error) { postSay(error.message); }", self.html)   # sending a comment
        self.assertIn("catch (error) { postSay(error.message); }", self.html)     # liking
        self.assertIn("commentEl(c, postSay)", self.html)                         # deleting a comment

    def test_typing_clears_the_old_error(self):
        self.assertIn('input.addEventListener("input", () => postSay(""))', self.html)

    def test_it_is_styled(self):
        self.assertIn(".post__message", self.css)

    def test_load_more_can_really_be_hidden(self):
        self.assertIn("#more[hidden] { display: none; }", self.css)


if __name__ == "__main__":
    unittest.main()

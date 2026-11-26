"""Sharing a post on the Community feed (shares.py, feed_api.py, community.html)."""

import unittest

from app import create_app
from models import Notification, PostShare, db
from notify_rules import SHARE, message
from shares import parse_share, share_target


class TestRules(unittest.TestCase):
    def test_words_are_optional(self):
        self.assertEqual(parse_share(None), "")
        self.assertEqual(parse_share({}), "")
        self.assertEqual(parse_share({"text": "  look at this  "}), "look at this")
        for bad in ({"text": 5}, {"text": "x" * 501}, "text"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                parse_share(bad)

    def test_sharing_a_share_shares_the_original(self):
        self.assertEqual(share_target(7, False, None), 7)
        self.assertEqual(share_target(9, True, 7), 7)
        with self.assertRaisesRegex(ValueError, "deleted"):
            share_target(9, True, None)

    def test_notification_words(self):
        self.assertEqual(message(SHARE, "ann", "Found it"), 'ann shared your post "Found it"')


class TestShareApi(unittest.TestCase):
    def setUp(self):
        self.app = create_app("sqlite:///:memory:")
        self.context = self.app.app_context()
        self.context.push()
        self.ann, self.bob, self.cat = (self.player(n) for n in ("ann", "bob", "cat"))
        self.post_id = self.bob.post("/api/posts", json={"text": "Found the lake treasure"}).get_json()["id"]

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
        self.context.pop()

    def player(self, name):
        client = self.app.test_client()
        client.post("/api/register", json={"username": name, "password": "secret1"})
        return client

    def share(self, client, post_id, text=None):
        return client.post(f"/api/posts/{post_id}/share", json={} if text is None else {"text": text})

    def test_needs_login_and_a_post(self):
        self.assertEqual(self.share(self.app.test_client(), self.post_id).status_code, 401)
        self.assertEqual(self.share(self.ann, 999).status_code, 404)

    def test_share_shows_the_original(self):
        r = self.share(self.ann, self.post_id, "Go find it!")
        self.assertEqual(r.status_code, 201)
        share = r.get_json()
        self.assertEqual((share["author"], share["text"], share["is_share"]), ("ann", "Go find it!", True))
        self.assertEqual((share["shared"]["author"], share["shared"]["text"]), ("bob", "Found the lake treasure"))

        feed = self.cat.get("/api/feed").get_json()["posts"]
        self.assertEqual([p["author"] for p in feed], ["ann", "bob"])
        self.assertEqual(feed[1]["share_count"], 1)
        self.assertFalse(feed[1]["is_share"])

    def test_the_author_is_told(self):
        self.share(self.ann, self.post_id)
        texts = [n["text"] for n in self.bob.get("/api/notifications").get_json()["items"]]
        self.assertEqual(texts, ['ann shared your post "Found the lake treasure"'])
        link = self.bob.get("/api/notifications").get_json()["items"][0]["link"]
        self.assertEqual(link, f"/posts/{self.post_id}")  # the shared post
        self.share(self.bob, self.post_id)  # sharing your own post: no notification
        self.assertEqual(db.session.query(Notification).filter_by(kind=SHARE).count(), 1)

    def test_sharing_a_share(self):
        first = self.share(self.ann, self.post_id).get_json()["id"]
        again = self.share(self.cat, first).get_json()
        self.assertEqual(again["shared"]["id"], self.post_id)  # the original, not ann's share

    def test_original_deleted(self):
        share_id = self.share(self.ann, self.post_id).get_json()["id"]
        self.assertEqual(self.bob.delete(f"/api/posts/{self.post_id}").status_code, 200)
        share = next(p for p in self.cat.get("/api/feed").get_json()["posts"] if p["id"] == share_id)
        self.assertEqual((share["is_share"], share["shared"]), (True, None))  # "This post was deleted"
        self.assertEqual(self.share(self.cat, share_id).status_code, 400)

    def test_deleting_your_share(self):
        share_id = self.share(self.ann, self.post_id).get_json()["id"]
        self.assertEqual(self.ann.delete(f"/api/posts/{share_id}").status_code, 200)
        self.assertEqual(db.session.query(PostShare).count(), 0)
        self.assertEqual(self.cat.get("/api/feed").get_json()["posts"][0]["share_count"], 0)

    def test_words_too_long(self):
        self.assertEqual(self.share(self.ann, self.post_id, "x" * 501).status_code, 400)

    def test_shares_count_as_posts_for_the_wait(self):
        self.app.config["SPAM_GAPS"] = {**self.app.config["SPAM_GAPS"], "post": 10}
        self.ann.post("/api/posts", json={"text": "hello"})
        self.assertEqual(self.share(self.ann, self.post_id).status_code, 429)


class TestPage(unittest.TestCase):
    def test_share_button_and_box(self):
        app = create_app("sqlite:///:memory:")
        client = app.test_client()
        client.post("/api/register", json={"username": "ann", "password": "secret1"})
        html = client.get("/community").get_data(as_text=True)
        with app.app_context():
            db.session.remove()
            db.drop_all()
            db.engine.dispose()
        self.assertIn("Share", html)
        self.assertIn("/share`", html)
        self.assertIn("This post was deleted.", html)
        self.assertIn("shared ${p.shared.author}'s post", html)
        self.assertNotIn(".innerHTML", html)


if __name__ == "__main__":
    unittest.main()

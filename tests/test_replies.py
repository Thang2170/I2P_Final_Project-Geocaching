"""Replying to a comment (feed_rules.py, feed_api.py, community.html)."""

import unittest

from app import create_app
from feed_rules import parse_reply, reply_start
from models import CommentReply, db
from notify_rules import REPLY, message
from rate_limit import MIN_GAP_S


class TestRules(unittest.TestCase):
    def test_parse_reply(self):
        self.assertEqual(parse_reply({"text": " thanks! "}), "thanks!")
        for bad in ({"text": "   "}, {"text": "x" * 301}, {}, None):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                parse_reply(bad)

    def test_reply_to_a_reply_starts_with_their_name(self):
        self.assertEqual(reply_start("bob"), "@bob ")

    def test_words(self):
        self.assertEqual(message(REPLY, "ann", "Found it"), 'ann replied to your comment on "Found it"')
        self.assertIn("reply", MIN_GAP_S)


class TestReplyApi(unittest.TestCase):
    def setUp(self):
        self.app = create_app("sqlite:///:memory:")
        self.context = self.app.app_context()
        self.context.push()
        self.ann, self.bob, self.cat = (self.player(n) for n in ("ann", "bob", "cat"))
        self.post_id = self.ann.post("/api/posts", json={"text": "Found the lake treasure"}).get_json()["id"]
        self.comment_id = self.bob.post(f"/api/posts/{self.post_id}/comments",
                                        json={"text": "Where exactly?"}).get_json()["id"]

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
        self.context.pop()

    def player(self, name):
        client = self.app.test_client()
        client.post("/api/register", json={"username": name, "password": "secret1"})
        return client

    def reply(self, client, text, comment_id=None):
        return client.post(f"/api/comments/{comment_id or self.comment_id}/replies", json={"text": text})

    def comment(self, client):
        posts = client.get("/api/feed").get_json()["posts"]
        return next(p for p in posts if p["id"] == self.post_id)["comments"][0]

    def test_needs_login_comment_and_words(self):
        self.assertEqual(self.reply(self.app.test_client(), "hi").status_code, 401)
        self.assertEqual(self.reply(self.ann, "hi", comment_id=999).status_code, 404)
        self.assertEqual(self.reply(self.ann, "   ").status_code, 400)

    def test_replies_show_under_the_comment(self):
        r = self.reply(self.ann, "By the big rock")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.get_json()["reply_start"], "@ann ")
        self.reply(self.cat, "@ann thanks!")
        replies = self.comment(self.bob)["replies"]
        self.assertEqual([(x["author"], x["text"]) for x in replies], [("ann", "By the big rock"), ("cat", "@ann thanks!")])
        self.assertEqual([x["mine"] for x in self.comment(self.ann)["replies"]], [True, False])

    def test_the_commenter_is_told(self):
        self.reply(self.ann, "By the big rock")
        texts = [n["text"] for n in self.bob.get("/api/notifications").get_json()["items"]]
        self.assertIn('ann replied to your comment on "Found the lake treasure"', texts)
        self.assertEqual(self.bob.get("/api/notifications").get_json()["items"][0]["link"], f"/posts/{self.post_id}")
        self.reply(self.bob, "ok")  # replying under your own comment: no notification for you
        self.assertEqual(len(self.bob.get("/api/notifications").get_json()["items"]), 1)

    def test_delete_a_reply(self):
        rid = self.reply(self.cat, "me too").get_json()["id"]
        self.assertEqual(self.ann.delete(f"/api/replies/{rid}").status_code, 403)
        self.assertEqual(self.cat.delete(f"/api/replies/{rid}").status_code, 200)
        self.assertEqual(self.comment(self.ann)["replies"], [])

    def test_deleting_the_comment_or_post_removes_replies(self):
        self.reply(self.ann, "one")
        self.bob.delete(f"/api/comments/{self.comment_id}")
        self.assertEqual(db.session.query(CommentReply).count(), 0)
        cid = self.bob.post(f"/api/posts/{self.post_id}/comments", json={"text": "again"}).get_json()["id"]
        self.reply(self.cat, "two", comment_id=cid)
        self.assertEqual(self.ann.delete(f"/api/posts/{self.post_id}").status_code, 200)
        self.assertEqual(db.session.query(CommentReply).count(), 0)

    def test_anti_spam(self):
        self.app.config["SPAM_GAPS"] = dict(MIN_GAP_S)
        self.assertEqual(self.reply(self.cat, "a").status_code, 201)
        self.assertEqual(self.reply(self.cat, "b").status_code, 429)


class TestPage(unittest.TestCase):
    def test_reply_links(self):
        app = create_app("sqlite:///:memory:")
        client = app.test_client()
        client.post("/api/register", json={"username": "ann", "password": "secret1"})
        html = client.get("/community").get_data(as_text=True)
        with app.app_context():
            db.session.remove()
            db.drop_all()
            db.engine.dispose()
        self.assertIn("function replyEl(", html)
        self.assertIn("/replies`", html)
        self.assertIn("answer(r.reply_start)", html)
        self.assertNotIn(".innerHTML", html)


if __name__ == "__main__":
    unittest.main()

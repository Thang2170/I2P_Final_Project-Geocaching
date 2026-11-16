"""Anti-spam: a short wait between posts, comments and chat messages."""

import unittest
from datetime import datetime, timedelta, timezone

from app import create_app
from models import db
from rate_limit import MIN_GAP_S, slow_down_message, wait_left

NOW = datetime(2026, 11, 15, 12, 0, tzinfo=timezone.utc)


class TestWaitLeft(unittest.TestCase):
    def test_never_sent_before(self):
        self.assertEqual(wait_left(None, NOW, 10), 0)

    def test_long_enough_ago(self):
        self.assertEqual(wait_left(NOW - timedelta(seconds=10), NOW, 10), 0)
        self.assertEqual(wait_left(NOW - timedelta(minutes=5), NOW, 10), 0)

    def test_too_soon_rounds_up(self):
        self.assertEqual(wait_left(NOW - timedelta(seconds=3), NOW, 10), 7)
        self.assertEqual(wait_left(NOW - timedelta(seconds=9.5), NOW, 10), 1)

    def test_times_from_sqlite_have_no_time_zone(self):
        last = (NOW - timedelta(seconds=2)).replace(tzinfo=None)
        self.assertEqual(wait_left(last, NOW, 3), 1)

    def test_a_gap_of_zero_means_no_wait(self):
        self.assertEqual(wait_left(NOW, NOW, 0), 0)

    def test_message(self):
        self.assertIn("1 second.", slow_down_message(1))
        self.assertIn("7 seconds.", slow_down_message(7))


class TestWaitsInTheApi(unittest.TestCase):
    def setUp(self):
        self.app = create_app("sqlite:///:memory:")
        self.app.config["SPAM_GAPS"] = dict(MIN_GAP_S)  # tests switch the waits off; switch them back on
        self.context = self.app.app_context()
        self.context.push()
        self.ann = self.app.test_client()
        self.ann.post("/api/register", json={"username": "ann", "password": "secret1"})

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
        self.context.pop()

    def test_two_posts_in_a_row_are_refused(self):
        self.assertEqual(self.ann.post("/api/posts", json={"text": "one"}).status_code, 201)
        r = self.ann.post("/api/posts", json={"text": "two"})
        self.assertEqual(r.status_code, 429)
        self.assertIn("Slow down", r.get_json()["error"])
        self.assertGreater(r.get_json()["wait_seconds"], 0)

    def test_two_comments_in_a_row_are_refused(self):
        pid = self.ann.post("/api/posts", json={"text": "hi"}).get_json()["id"]
        self.assertEqual(self.ann.post(f"/api/posts/{pid}/comments", json={"text": "a"}).status_code, 201)
        self.assertEqual(self.ann.post(f"/api/posts/{pid}/comments", json={"text": "b"}).status_code, 429)

    def test_two_chat_messages_in_a_row_are_refused(self):
        hid = self.ann.post("/api/hunts", json={"name": "Walk"}).get_json()["id"]
        self.assertEqual(self.ann.post(f"/api/hunts/{hid}/messages", json={"text": "a"}).status_code, 201)
        self.assertEqual(self.ann.post(f"/api/hunts/{hid}/messages", json={"text": "b"}).status_code, 429)

    def test_the_wait_is_per_player(self):
        self.ann.post("/api/posts", json={"text": "one"})
        bob = self.app.test_client()
        bob.post("/api/register", json={"username": "bob", "password": "secret1"})
        self.assertEqual(bob.post("/api/posts", json={"text": "mine"}).status_code, 201)

    def test_a_refused_post_is_not_saved_and_bad_text_still_says_why(self):
        self.ann.post("/api/posts", json={"text": "one"})
        self.ann.post("/api/posts", json={"text": "two"})
        self.assertEqual(len(self.ann.get("/api/feed").get_json()["posts"]), 1)
        self.assertEqual(self.ann.post("/api/posts", json={"text": ""}).status_code, 400)  # empty: 400 first


if __name__ == "__main__":
    unittest.main()

"""The notifications bell: likes, comments, and moving up from a waiting line."""

import unittest

from app import create_app
from models import Notification, db
from notify_rules import COMMENT, LIKE, MOVED_UP, link, message, moved_up, short, should_notify


class TestRules(unittest.TestCase):
    def test_no_notifications_about_yourself(self):
        self.assertFalse(should_notify(1, 1))
        self.assertTrue(should_notify(1, 2))

    def test_messages(self):
        self.assertEqual(message(LIKE, "ann", "hi"), 'ann liked your post "hi"')
        self.assertEqual(message(COMMENT, "bob", "hi"), 'bob commented on your post "hi"')
        self.assertIn('You moved up in "Night walk"', message(MOVED_UP, None, "Night walk"))
        with self.assertRaises(ValueError):
            message("party", "ann", "x")

    def test_links(self):
        self.assertEqual(link(LIKE, post_id=3), "/community")
        self.assertEqual(link(MOVED_UP, hunt_id=7), "/hunts/7/chat")

    def test_short(self):
        self.assertEqual(short("hi"), "hi")
        self.assertEqual(short("a  b\nc"), "a b c")
        self.assertEqual(len(short("x" * 100)), 40)
        self.assertTrue(short("x" * 100).endswith("…"))

    def test_moved_up(self):
        # capacity 2: members 1, 2 play; 3, 4 wait. 1 leaves: 3 moves up, 4 still waits.
        self.assertEqual(moved_up([1, 2, 3, 4], [2, 3, 4], 2), [3])
        # someone who was waiting leaves: nobody moves up
        self.assertEqual(moved_up([1, 2, 3, 4], [1, 2, 4], 2), [])


class TestNotificationsApi(unittest.TestCase):
    def setUp(self):
        self.app = create_app("sqlite:///:memory:")
        self.context = self.app.app_context()
        self.context.push()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
        self.context.pop()

    def player(self, name):
        client = self.app.test_client()
        client.post("/api/register", json={"username": name, "password": "secret1"})
        return client

    def bell(self, client):
        return client.get("/api/notifications").get_json()

    def test_needs_a_login(self):
        guest = self.app.test_client()
        self.assertEqual(guest.get("/api/notifications").status_code, 401)
        self.assertEqual(guest.post("/api/notifications/seen").status_code, 401)

    def test_a_like_and_a_comment_reach_the_author(self):
        ann, bob = self.player("ann"), self.player("bob")
        pid = ann.post("/api/posts", json={"text": "Found the pond treasure!"}).get_json()["id"]
        bob.post(f"/api/posts/{pid}/like")
        bob.post(f"/api/posts/{pid}/comments", json={"text": "Nice"})
        data = self.bell(ann)
        self.assertEqual(data["unseen"], 2)
        self.assertEqual([n["text"] for n in data["items"]],
                         ['bob commented on your post "Found the pond treasure!"',
                          'bob liked your post "Found the pond treasure!"'])
        self.assertEqual(data["items"][0]["link"], "/community")
        self.assertEqual(self.bell(bob)["unseen"], 0)

    def test_your_own_like_or_comment_makes_no_notification(self):
        ann = self.player("ann")
        pid = ann.post("/api/posts", json={"text": "hi"}).get_json()["id"]
        ann.post(f"/api/posts/{pid}/like")
        ann.post(f"/api/posts/{pid}/comments", json={"text": "me again"})
        self.assertEqual(self.bell(ann)["items"], [])

    def test_like_unlike_like_makes_one_notification(self):
        ann, bob = self.player("ann"), self.player("bob")
        pid = ann.post("/api/posts", json={"text": "hi"}).get_json()["id"]
        for _ in range(3):
            bob.post(f"/api/posts/{pid}/like")
        self.assertEqual(self.bell(ann)["unseen"], 1)

    def test_opening_the_bell_marks_them_seen(self):
        ann, bob = self.player("ann"), self.player("bob")
        pid = ann.post("/api/posts", json={"text": "hi"}).get_json()["id"]
        bob.post(f"/api/posts/{pid}/like")
        self.assertEqual(ann.post("/api/notifications/seen").get_json(), {"unseen": 0})
        data = self.bell(ann)
        self.assertEqual((data["unseen"], data["items"][0]["seen"]), (0, True))

    def test_moving_up_from_the_line(self):
        ann, bob = self.player("ann"), self.player("bob")
        hid = ann.post("/api/hunts", json={"name": "Night walk", "capacity": 1}).get_json()["id"]
        bob.post(f"/api/hunts/{hid}/join")   # full: bob waits
        ann.post(f"/api/hunts/{hid}/leave")  # bob moves up
        item = self.bell(bob)["items"][0]
        self.assertIn('You moved up in "Night walk"', item["text"])
        self.assertEqual(item["link"], f"/hunts/{hid}/chat")
        self.assertIsNone(item["avatar"])

    def test_deleting_a_post_removes_its_notifications(self):
        ann, bob = self.player("ann"), self.player("bob")
        pid = ann.post("/api/posts", json={"text": "hi"}).get_json()["id"]
        bob.post(f"/api/posts/{pid}/like")
        ann.delete(f"/api/posts/{pid}")
        self.assertEqual(db.session.query(Notification).count(), 0)

    def test_the_bell_is_in_the_top_bar(self):
        html = self.app.test_client().get("/community").get_data(as_text=True)
        self.assertIn('id="bell"', html)
        self.assertIn("/api/notifications", html)
        self.assertNotIn(".innerHTML", html)


if __name__ == "__main__":
    unittest.main()

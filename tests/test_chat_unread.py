"""The Hunts page shows how many group-chat messages you haven't read."""

import unittest

from app import create_app
from hunt_chat import unread_count
from models import db


class TestUnreadCount(unittest.TestCase):
    def test_counts_newer_messages_from_others(self):
        messages = [(1, 2), (2, 1), (3, 2), (4, 3)]  # (message id, sender id)
        self.assertEqual(unread_count(messages, 0, 1), 3)   # never opened: all but my own
        self.assertEqual(unread_count(messages, 2, 1), 2)   # read up to 2
        self.assertEqual(unread_count(messages, 4, 1), 0)   # read everything

    def test_your_own_messages_never_count(self):
        self.assertEqual(unread_count([(5, 1), (6, 1)], 0, 1), 0)


class TestUnreadApi(unittest.TestCase):
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

    def unread(self, client, hunt_id):
        return next(h for h in client.get("/api/hunts").get_json() if h["id"] == hunt_id)["unread"]

    def test_new_messages_show_up_then_clear_when_you_open_the_chat(self):
        ann, bob = self.player("ann"), self.player("bob")
        hid = ann.post("/api/hunts", json={"name": "Walk"}).get_json()["id"]
        bob.post(f"/api/hunts/{hid}/join")
        ann.post(f"/api/hunts/{hid}/messages", json={"text": "hi"})
        ann.post(f"/api/hunts/{hid}/messages", json={"text": "gate at 5?"})
        self.assertEqual(self.unread(bob, hid), 2)
        self.assertEqual(self.unread(ann, hid), 0)  # her own messages
        bob.get(f"/api/hunts/{hid}/messages")      # bob opens the chat
        self.assertEqual(self.unread(bob, hid), 0)
        ann.post(f"/api/hunts/{hid}/messages", json={"text": "see you"})
        self.assertEqual(self.unread(bob, hid), 1)

    def test_no_count_for_people_in_line_or_outside(self):
        ann, bob, cyd = self.player("ann"), self.player("bob"), self.player("cyd")
        hid = ann.post("/api/hunts", json={"name": "Tiny", "capacity": 1}).get_json()["id"]
        bob.post(f"/api/hunts/{hid}/join")  # full: bob waits in line
        ann.post(f"/api/hunts/{hid}/messages", json={"text": "hi"})
        self.assertEqual(self.unread(bob, hid), 0)
        self.assertEqual(self.unread(cyd, hid), 0)
        self.assertEqual(self.unread(self.app.test_client(), hid), 0)  # logged out

    def test_the_page_shows_the_badge_and_refreshes(self):
        c = self.app.test_client()
        c.post("/api/register", json={"username": "pagecheck", "password": "secret1"})  # B: /hunts needs a login now
        html = c.get("/hunts").get_data(as_text=True)
        self.assertIn("unread-badge", html)
        self.assertIn("setInterval", html)


if __name__ == "__main__":
    unittest.main()

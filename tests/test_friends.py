"""Friends: both players must agree (friends.py, friends_api.py, the bell and the feed switch)."""

import unittest

from app import create_app
from friends import (ACCEPTED, FRIENDS, NONE, PENDING, RECEIVED, SELF, SENT, check_answer, check_remove,
                     friend_ids, parse_feed_filter, relation, request_action)
from models import Friendship, Notification, db
from notify_rules import FRIEND_ACCEPTED, FRIEND_REQUEST, link, message


class TestRules(unittest.TestCase):
    def test_relation(self):
        self.assertEqual(relation(1, 1, None), SELF)
        self.assertEqual(relation(1, 2, None), NONE)
        self.assertEqual(relation(1, 2, (1, 2, PENDING)), SENT)
        self.assertEqual(relation(2, 1, (1, 2, PENDING)), RECEIVED)
        self.assertEqual(relation(2, 1, (1, 2, ACCEPTED)), FRIENDS)

    def test_add_friend(self):
        self.assertEqual(request_action(1, 2, None), "create")
        self.assertEqual(request_action(2, 1, (1, 2, PENDING)), "accept")  # you both asked: friends
        for me, other, row, words in ((1, 1, None, "yourself"), (1, 2, (1, 2, PENDING), "already asked"),
                                      (1, 2, (2, 1, ACCEPTED), "already friends")):
            with self.subTest(words=words), self.assertRaisesRegex(ValueError, words):
                request_action(me, other, row)

    def test_answer_and_remove(self):
        check_answer(2, 1, (1, 2, PENDING))
        with self.assertRaises(ValueError):
            check_answer(1, 2, (1, 2, PENDING))  # you can't accept your own request
        check_remove(1, 2, (1, 2, PENDING))      # take back a request
        check_remove(2, 1, (1, 2, ACCEPTED))     # unfriend
        with self.assertRaises(ValueError):
            check_remove(1, 2, None)

    def test_friend_ids(self):
        rows = [(1, 2, ACCEPTED), (3, 1, ACCEPTED), (1, 4, PENDING), (5, 6, ACCEPTED)]
        self.assertEqual(friend_ids(1, rows), [2, 3])

    def test_feed_filter(self):
        self.assertEqual(parse_feed_filter(None), "everyone")
        self.assertEqual(parse_feed_filter(" Friends "), "friends")
        with self.assertRaises(ValueError):
            parse_feed_filter("enemies")

    def test_notification_words(self):
        self.assertEqual(message(FRIEND_REQUEST, "ann", ""), "ann wants to be your friend")
        self.assertEqual(message(FRIEND_ACCEPTED, "bob", ""), "bob accepted your friend request")
        self.assertEqual(link(FRIEND_REQUEST, actor_name="ann"), "/players/ann")


class TestFriendsApi(unittest.TestCase):
    def setUp(self):
        self.app = create_app("sqlite:///:memory:")
        self.context = self.app.app_context()
        self.context.push()
        self.ann, self.bob, self.cat = (self.player(n) for n in ("ann", "bob", "cat"))

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
        self.context.pop()

    def player(self, name):
        client = self.app.test_client()
        client.post("/api/register", json={"username": name, "password": "secret1"})
        return client

    def state(self, client, name):
        return client.get(f"/api/players/{name}/friends").get_json()["state"]

    def bell(self, client):
        return client.get("/api/notifications").get_json()["items"]

    def test_needs_login_and_a_real_player(self):
        guest = self.app.test_client()
        self.assertEqual(guest.post("/api/friends/bob/request").status_code, 401)
        self.assertEqual(guest.get("/api/players/bob/friends").status_code, 401)
        self.assertEqual(self.ann.post("/api/friends/nobody/request").status_code, 404)
        self.assertEqual(self.ann.post("/api/friends/no%20one/request").status_code, 404)

    def test_ask_and_accept(self):
        r = self.ann.post("/api/friends/bob/request")
        self.assertEqual((r.status_code, r.get_json()["state"]), (201, SENT))
        self.assertEqual(self.state(self.bob, "ann"), RECEIVED)

        item = self.bell(self.bob)[0]
        self.assertEqual(item["text"], "ann wants to be your friend")
        self.assertEqual(item["friend_request"], {"username": "ann", "waiting": True})

        self.assertEqual(self.bob.post("/api/friends/ann/accept").get_json()["state"], FRIENDS)
        self.assertEqual(self.state(self.ann, "bob"), FRIENDS)
        self.assertEqual(self.bell(self.bob), [])  # the answered request leaves the bell
        self.assertEqual(self.bell(self.ann)[0]["text"], "bob accepted your friend request")

        lists = self.cat.get("/api/players/ann/friends").get_json()  # anyone logged in can see the list
        self.assertEqual(([f["username"] for f in lists["friends"]], lists["count"], lists["state"]),
                         (["bob"], 1, NONE))

    def test_asking_twice_or_yourself(self):
        self.ann.post("/api/friends/bob/request")
        self.assertEqual(self.ann.post("/api/friends/bob/request").status_code, 400)
        self.assertEqual(self.ann.post("/api/friends/ann/request").status_code, 400)
        self.assertEqual(db.session.query(Friendship).count(), 1)

    def test_both_ask_means_friends(self):
        self.ann.post("/api/friends/bob/request")
        self.assertEqual(self.bob.post("/api/friends/ann/request").get_json()["state"], FRIENDS)

    def test_only_the_asked_player_can_answer(self):
        self.ann.post("/api/friends/bob/request")
        self.assertEqual(self.ann.post("/api/friends/bob/accept").status_code, 400)
        self.assertEqual(self.cat.post("/api/friends/ann/accept").status_code, 400)

    def test_decline(self):
        self.ann.post("/api/friends/bob/request")
        self.assertEqual(self.bob.post("/api/friends/ann/decline").get_json()["state"], NONE)
        self.assertEqual(self.state(self.ann, "bob"), NONE)  # ann can ask again later
        self.assertEqual(self.bell(self.bob), [])
        self.assertEqual(self.ann.post("/api/friends/bob/request").status_code, 201)

    def test_cancel_and_unfriend(self):
        self.ann.post("/api/friends/bob/request")
        self.assertEqual(self.ann.post("/api/friends/bob/remove").get_json()["state"], NONE)
        self.assertEqual(db.session.query(Notification).filter_by(kind=FRIEND_REQUEST).count(), 0)
        self.ann.post("/api/friends/bob/request")
        self.bob.post("/api/friends/ann/accept")
        self.assertEqual(self.bob.post("/api/friends/ann/remove").get_json()["state"], NONE)
        self.assertEqual(self.bob.post("/api/friends/ann/remove").status_code, 400)

    def test_requests_waiting_on_your_own_profile(self):
        self.ann.post("/api/friends/cat/request")
        self.bob.post("/api/friends/cat/request")
        mine = self.cat.get("/api/players/cat/friends").get_json()
        self.assertEqual((mine["state"], mine["requests_waiting"]), (SELF, 2))
        self.assertEqual(self.ann.get("/api/players/cat/friends").get_json()["requests_waiting"], 0)

    def test_friends_feed(self):
        for client, words in ((self.ann, "from ann"), (self.bob, "from bob"), (self.cat, "from cat")):
            client.post("/api/posts", json={"text": words})
        self.ann.post("/api/friends/bob/request")
        self.bob.post("/api/friends/ann/accept")
        texts = lambda q: [p["text"] for p in self.ann.get(f"/api/feed{q}").get_json()["posts"]]
        self.assertEqual(texts(""), ["from cat", "from bob", "from ann"])
        self.assertEqual(texts("?only=friends"), ["from bob", "from ann"])
        self.assertEqual(self.ann.get("/api/feed?only=foes").status_code, 400)


class TestPages(unittest.TestCase):
    def setUp(self):
        self.app = create_app("sqlite:///:memory:")
        client = self.app.test_client()
        client.post("/api/register", json={"username": "ann", "password": "secret1"})
        self.profile = client.get("/players/ann").get_data(as_text=True)
        self.community = client.get("/community").get_data(as_text=True)

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()
            db.engine.dispose()

    def test_profile_has_friends(self):
        self.assertIn('id="friendActions"', self.profile)
        self.assertIn('id="friendList"', self.profile)
        self.assertIn("/friends`", self.profile)
        self.assertIn("Add friend", self.profile)  # the bell (in the top bar) has Accept / Decline
        self.assertIn("friendButtons(n.friend_request)", self.profile)

    def test_feed_switch(self):
        self.assertIn('data-only="friends"', self.community)
        self.assertIn("&only=${feedOnly}", self.community)
        self.assertNotIn(".innerHTML", self.community)
        self.assertNotIn(".innerHTML", self.profile)


if __name__ == "__main__":
    unittest.main()

import unittest

from app import create_app
from coin_api import get_balance
from demo_content import (BUILT_IN_TREASURE_NAME, DEMO_CHAT, DEMO_CHAT_HUNT, DEMO_FULL_HUNT, DEMO_JOURNEYS,
                          DEMO_PASSWORD, DEMO_POSTS, DEMO_RATINGS, DEMO_SHARES, DEMO_TREASURES, DEMO_USERS)
from demo_data import seed_demo_story
from models import (DEMO_TREASURE, Hunt, HuntMember, HuntMessage, Journey, Post, PostComment, PostLike, Profile,
                    Treasure, User, db)
from queue_logic import queue_status


class TestDemoData(unittest.TestCase):
    def setUp(self):
        self.app = create_app("sqlite:///:memory:")
        self.context = self.app.app_context()
        self.context.push()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
        self.context.pop()

    def user(self, username):
        return db.session.query(User).filter_by(username=username).one()

    def test_saves_the_users_with_a_working_password_and_weight(self):
        seed_demo_story()
        for spec in DEMO_USERS:
            user = self.user(spec["username"])
            self.assertTrue(user.check_password(DEMO_PASSWORD))
            self.assertEqual(db.session.get(Profile, user.id).weight_kg, spec["weight_kg"])
            self.assertEqual(get_balance(user.id), spec["coins"])

    def test_saves_the_treasures_hidden_by_alice(self):
        seed_demo_story()
        alice = self.user("alice")
        for spec in DEMO_TREASURES:
            treasure = db.session.query(Treasure).filter_by(name=spec["name"]).one()
            self.assertEqual(treasure.created_by, alice.id)

    def test_the_full_hunt_makes_a_new_player_wait(self):
        seed_demo_story()
        hunt = db.session.query(Hunt).filter_by(name=DEMO_FULL_HUNT["name"]).one()
        members = db.session.query(HuntMember).filter_by(hunt_id=hunt.id).order_by(HuntMember.id).all()
        self.assertEqual([m.user_id for m in members],
                         [self.user(name).id for name in DEMO_FULL_HUNT["members"]])
        ids = [m.user_id for m in members] + [self.user("demo_player").id]
        self.assertEqual(queue_status(ids[-1], ids, hunt.capacity), {"state": "waiting", "position": 1})

    def test_running_it_twice_adds_nothing_the_second_time(self):
        seed_demo_story()
        counts = [db.session.query(model).count() for model in (User, Treasure, Hunt, HuntMember)]
        again = seed_demo_story()
        self.assertEqual(again, {"users": [], "treasures": [], "hunts": [], "journeys": [], "posts": [], "chat": [], "social": []})
        self.assertEqual(counts, [db.session.query(m).count() for m in (User, Treasure, Hunt, HuntMember)])
        self.assertEqual(get_balance(self.user("demo_player").id), DEMO_USERS[0]["coins"])

    def test_never_resets_a_balance_or_password_that_changed(self):
        seed_demo_story()
        player = self.user("demo_player")
        player.set_password("something-new")
        db.session.commit()
        seed_demo_story()
        self.assertTrue(self.user("demo_player").check_password("something-new"))

    def test_the_built_in_treasure_name_matches_the_database_seed(self):
        self.assertEqual(BUILT_IN_TREASURE_NAME, DEMO_TREASURE["name"])

    def test_saves_the_demo_hunts_with_steps_and_calories_from_python(self):
        seed_demo_story()
        self.assertEqual(db.session.query(Journey).count(), len(DEMO_JOURNEYS))
        ben = self.user("ben")
        pond = db.session.query(Treasure).filter_by(name="Pond bench").one()
        saved = db.session.query(Journey).filter_by(user_id=ben.id, treasure_id=pond.id).one()
        self.assertEqual((saved.distance_m, saved.duration_s), (180, 250))
        self.assertEqual(saved.steps, 240)                 # 180 m / 0.75 m per step
        self.assertEqual(saved.calories, 6.3)              # 0.5 * 70 kg * 0.18 km

    def test_running_it_twice_does_not_duplicate_the_hunts(self):
        seed_demo_story()
        seed_demo_story()
        self.assertEqual(db.session.query(Journey).count(), len(DEMO_JOURNEYS))

    def test_the_feed_has_posts_likes_and_comments(self):
        seed_demo_story()
        # the written posts, one post per finished hunt, and the shares (a share is a post too)
        self.assertEqual(db.session.query(Post).count(), len(DEMO_POSTS) + len(DEMO_JOURNEYS) + len(DEMO_SHARES))
        self.assertGreater(db.session.query(PostLike).count(), 0)
        self.assertGreater(db.session.query(PostComment).count(), 0)
        player = self.app.test_client()
        player.post("/api/login", json={"username": "demo_player", "password": DEMO_PASSWORD})
        posts = player.get("/api/feed").get_json()["posts"]
        alice_post = next(p for p in posts if p["author"] == "alice" and p["hunt"] is None)
        self.assertTrue(alice_post["liked_by_me"])
        self.assertEqual(alice_post["comment_count"], 2)

    def test_social_demo(self):
        seed_demo_story()
        seed_demo_story()  # twice: nothing doubles
        player = self.app.test_client()
        player.post("/api/login", json={"username": "demo_player", "password": DEMO_PASSWORD})
        bell = player.get("/api/notifications").get_json()["items"]
        self.assertEqual([n["friend_request"] for n in bell if n["friend_request"]],
                         [{"username": "ben", "waiting": True}])
        self.assertEqual(player.get("/api/players/alice/friends").get_json()["count"], 1)
        ranks = player.get("/api/treasures/rankings").get_json()
        self.assertEqual(len(ranks["top_rated"]), len(DEMO_RATINGS))
        self.assertTrue(ranks["trending"])
        posts = player.get("/api/feed").get_json()["posts"]
        share = next(p for p in posts if p["is_share"])
        self.assertEqual((share["author"], share["shared"]["author"]), ("ben", "alice"))
        alice_post = next(p for p in posts if p["author"] == "alice" and p["hunt"] is None)
        replies = [r for c in alice_post["comments"] for r in c["replies"]]
        self.assertEqual([r["author"] for r in replies], ["demo_player"])

    def test_running_it_twice_does_not_duplicate_the_feed(self):
        seed_demo_story()
        counts = [db.session.query(m).count() for m in (Post, PostLike, PostComment)]
        seed_demo_story()
        self.assertEqual(counts, [db.session.query(m).count() for m in (Post, PostLike, PostComment)])

    def test_the_demo_hunt_has_a_chat_demo_player_can_read(self):
        seed_demo_story()
        player = self.app.test_client()
        player.post("/api/login", json={"username": "demo_player", "password": DEMO_PASSWORD})
        hunts = player.get("/api/hunts").get_json()
        walk = next(h for h in hunts if h["name"] == DEMO_CHAT_HUNT)
        player.post(f"/api/hunts/{walk['id']}/join")  # 2 of 5 places taken: demo_player plays
        data = player.get(f"/api/hunts/{walk['id']}/messages").get_json()
        self.assertEqual([m["text"] for m in data["messages"]], [t for _, t in DEMO_CHAT["messages"]])

    def test_demo_player_does_not_get_the_tour_mid_demo(self):
        seed_demo_story()
        player = self.app.test_client()
        player.post("/api/login", json={"username": "demo_player", "password": DEMO_PASSWORD})
        self.assertFalse(player.get("/api/onboarding").get_json()["show"])
        self.assertTrue(player.get("/api/onboarding?again=1").get_json()["show"])  # /?tour still works

    def test_running_it_twice_does_not_duplicate_the_chat(self):
        seed_demo_story()
        count = db.session.query(HuntMessage).count()
        seed_demo_story()
        self.assertEqual(db.session.query(HuntMessage).count(), count)


if __name__ == "__main__":
    unittest.main()

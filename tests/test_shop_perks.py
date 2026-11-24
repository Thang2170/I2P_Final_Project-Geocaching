import unittest

from app import create_app
from models import CoinTransaction, Post, PostComment, User, db
from shop import BADGE, GOLD_PIN, perks


class TestPerksRule(unittest.TestCase):
    def test_nothing_owned(self):
        self.assertEqual(perks([]), {"badge": False, "gold_pin": False})

    def test_each_item_turns_on_its_perk(self):
        self.assertEqual(perks([BADGE]), {"badge": True, "gold_pin": False})
        self.assertEqual(perks([GOLD_PIN, "bubble-tea"]), {"badge": False, "gold_pin": True})


class TestPerksApi(unittest.TestCase):
    def setUp(self):
        # The real app on a throwaway database
        self.app = create_app("sqlite:///:memory:")
        self.context = self.app.app_context()
        self.context.push()
        self.bao = self.player("bao", coins=100)
        self.lan = self.player("lan")

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
        self.context.pop()

    def player(self, name, coins=0):
        client = self.app.test_client()
        client.post("/api/register", json={"username": name, "password": "secret1"})
        if coins:
            user_id = db.session.execute(db.select(User.id).filter_by(username=name)).scalar_one()
            db.session.add(CoinTransaction(user_id=user_id, amount=coins, reason="test_gift"))
            db.session.commit()
        return client

    def test_my_perks_needs_a_login(self):
        self.assertEqual(self.app.test_client().get("/api/me/perks").status_code, 401)

    def test_my_perks_change_after_buying(self):
        self.assertEqual(self.bao.get("/api/me/perks").get_json(), {"badge": False, "gold_pin": False})
        self.assertEqual(self.bao.post("/api/shop/buy", json={"item_id": GOLD_PIN}).status_code, 200)
        self.assertEqual(self.bao.get("/api/me/perks").get_json(), {"badge": False, "gold_pin": True})

    def test_profile_shows_the_badge_only_after_buying(self):
        self.assertFalse(self.lan.get("/api/players/bao").get_json()["badge"])
        self.bao.post("/api/shop/buy", json={"item_id": BADGE})
        self.assertTrue(self.lan.get("/api/players/bao").get_json()["badge"])  # others see it too
        self.assertFalse(self.bao.get("/api/players/lan").get_json()["badge"])

    def test_feed_marks_badge_owners_on_posts_and_comments(self):
        self.bao.post("/api/shop/buy", json={"item_id": BADGE})
        self.bao.post("/api/posts", json={"text": "Badge time"})
        post_id = db.session.execute(db.select(Post.id)).scalar_one()
        self.lan.post(f"/api/posts/{post_id}/comments", json={"text": "Nice"})
        self.assertEqual(len(db.session.execute(db.select(PostComment.id)).scalars().all()), 1)

        post = next(p for p in self.lan.get("/api/feed").get_json()["posts"] if p["id"] == post_id)
        self.assertTrue(post["author_badge"])             # bao bought it
        self.assertFalse(post["comments"][0]["author_badge"])  # lan didn't


if __name__ == "__main__":
    unittest.main()

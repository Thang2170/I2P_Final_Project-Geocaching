import unittest

from flask import Flask

from auth_api import auth_api
from coin_api import FOUND_REASON
from leaderboard_api import leaderboard_api
from models import CoinTransaction, Treasure, User, db


class TestLeaderboardApi(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
        self.app.config["SECRET_KEY"] = "test-key"
        db.init_app(self.app)
        self.app.register_blueprint(auth_api)
        self.app.register_blueprint(leaderboard_api)
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
        self.context.pop()

    def add_user(self, username):
        user = User(username=username)
        db.session.add(user)
        db.session.commit()
        return user

    def test_page_uses_shared_style_and_is_highlighted(self):
        html = self.client.get("/leaderboard").get_data(as_text=True)
        self.assertIn("css/app.css", html)
        self.assertIn('href="/leaderboard" class="is-active"', html)

    def test_no_players_gives_an_empty_list(self):
        self.assertEqual(self.client.get("/api/leaderboard").get_json(), [])

    def test_players_are_ranked_by_coins_with_their_counts(self):
        alice = self.add_user("alice")
        ben = self.add_user("ben")
        t1 = Treasure(name="A", lat=24.79, lon=120.99, created_by=alice.id)
        t2 = Treasure(name="B", lat=24.80, lon=120.99, created_by=alice.id)
        db.session.add_all([t1, t2])
        db.session.commit()
        # ben found both of alice's treasures (10 coins each) and then spent 5 in the shop
        db.session.add_all([
            CoinTransaction(user_id=ben.id, amount=10, reason=FOUND_REASON, treasure_id=t1.id),
            CoinTransaction(user_id=ben.id, amount=10, reason=FOUND_REASON, treasure_id=t2.id),
            CoinTransaction(user_id=ben.id, amount=-5, reason="shop"),
        ])
        db.session.commit()

        rows = self.client.get("/api/leaderboard").get_json()
        self.assertEqual(rows[0], {"rank": 1, "username": "ben", "coins": 15, "found": 2, "hidden": 0})
        self.assertEqual(rows[1], {"rank": 2, "username": "alice", "coins": 0, "found": 0, "hidden": 2})

    def test_anyone_can_see_it_without_logging_in(self):
        self.add_user("alice")
        self.assertEqual(self.client.get("/api/leaderboard").status_code, 200)


if __name__ == "__main__":
    unittest.main()

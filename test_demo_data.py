import unittest

from app import create_app
from coin_api import get_balance
from demo_content import DEMO_FULL_HUNT, DEMO_PASSWORD, DEMO_TREASURES, DEMO_USERS
from demo_data import seed_demo_story
from models import Hunt, HuntMember, Profile, Treasure, User, db
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
        self.assertEqual(again, {"users": [], "treasures": [], "hunts": []})
        self.assertEqual(counts, [db.session.query(m).count() for m in (User, Treasure, Hunt, HuntMember)])
        self.assertEqual(get_balance(self.user("demo_player").id), DEMO_USERS[0]["coins"])

    def test_never_resets_a_balance_or_password_that_changed(self):
        seed_demo_story()
        player = self.user("demo_player")
        player.set_password("something-new")
        db.session.commit()
        seed_demo_story()
        self.assertTrue(self.user("demo_player").check_password("something-new"))


if __name__ == "__main__":
    unittest.main()

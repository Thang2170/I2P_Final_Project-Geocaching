"""B: demo data for the heat map, the race replay and rain / night treasures (demo_extras.py)."""

import unittest

from app import create_app
from demo_data import seed_demo_story
from demo_extras import DEMO_CONDITION_TREASURES, DEMO_RACE, DEMO_WALKERS, seed_demo_extras
from location import haversine_m
from models import HeatVisit, Hunt, RacePoint, Treasure, TreasureCondition, User, db
from treasure_input import MIN_TREASURE_GAP_M as MIN_GAP_M


class DemoExtrasTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app("sqlite:///:memory:")
        self.ctx = self.app.app_context()
        self.ctx.push()
        self.added = seed_demo_story()["extras"]

    def tearDown(self):
        db.session.remove()
        self.ctx.pop()

    def test_everything_is_there(self):
        for name in DEMO_WALKERS:
            self.assertIsNotNone(db.session.execute(db.select(User).filter_by(username=name)).scalar())
        self.assertEqual(db.session.query(Hunt).filter_by(name=DEMO_RACE["name"]).count(), 1)
        self.assertGreater(db.session.query(RacePoint).count(), 0)
        self.assertGreater(db.session.query(HeatVisit).count(), 0)
        self.assertEqual(sorted(c.condition for c in db.session.query(TreasureCondition)),
                         sorted(s["condition"] for s in DEMO_CONDITION_TREASURES))
        self.assertIn(f"race {DEMO_RACE['name']}", self.added)

    def test_running_it_again_adds_nothing(self):
        counts = [db.session.query(m).count() for m in (User, Hunt, RacePoint, HeatVisit, Treasure)]
        self.assertEqual(seed_demo_extras(), [])
        self.assertEqual(counts, [db.session.query(m).count() for m in (User, Hunt, RacePoint, HeatVisit, Treasure)])

    def test_the_new_treasures_keep_their_distance(self):
        names = {s["name"] for s in DEMO_CONDITION_TREASURES}
        treasures = db.session.query(Treasure).all()
        for new in (t for t in treasures if t.name in names):
            for other in treasures:
                if other.id != new.id:
                    self.assertGreaterEqual(haversine_m(new.lat, new.lon, other.lat, other.lon), MIN_GAP_M,
                                            f"{new.name} is too close to {other.name}")

    def test_walkers_can_log_in(self):
        c = self.app.test_client()
        self.assertEqual(c.post("/api/login", json={"username": DEMO_WALKERS[0], "password": "demo1234"}).status_code, 200)


if __name__ == "__main__":
    unittest.main()

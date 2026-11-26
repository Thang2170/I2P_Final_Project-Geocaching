"""B: hunt race replays (replay.py, replay_api.py)."""

import unittest
from datetime import datetime, timedelta, timezone

from app import create_app
from hunt_game_api import HuntGame
from models import Hunt, HuntMember, RacePoint, Treasure, User, db
from replay import (MAX_POINTS, MAX_SPEED, MIN_GAP_S, REPLAY_LENGTH_S, build_replay, clock, headline,
                    replay_problem, should_keep, speed_for)


def _utc_now():
    """Naive UTC, like the database keeps (datetime.utcnow() is deprecated in Python 3.12+)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


T0 = datetime(2026, 11, 20, 8, 0, 0)
TREASURE = {"name": "Pond", "lat": 24.7950, "lon": 120.9950}


class ReplayRulesTest(unittest.TestCase):
    def test_keeps_one_point_every_few_seconds(self):
        self.assertTrue(should_keep(None, T0, 0))
        self.assertFalse(should_keep(T0, T0 + timedelta(seconds=MIN_GAP_S - 1), 3))
        self.assertTrue(should_keep(T0, T0 + timedelta(seconds=MIN_GAP_S), 3))
        self.assertFalse(should_keep(T0, T0 + timedelta(hours=1), MAX_POINTS))

    def test_speed_makes_any_race_about_twenty_seconds(self):
        self.assertEqual(speed_for(10), 1)
        self.assertEqual(speed_for(150), 8)               # 150 s -> under 20 s
        self.assertLessEqual(150 / speed_for(150), REPLAY_LENGTH_S)
        self.assertEqual(speed_for(10 * 3600), MAX_SPEED)

    def test_clock(self):
        self.assertEqual(clock(185), "3:05")
        self.assertEqual(clock(-3), "0:00")

    def test_build_replay(self):
        paths = {
            "zed": [(T0 + timedelta(seconds=s), 24.7960, 120.9950 + s * 1e-6) for s in (0, 5, 10)],
            "ben": [(T0 + timedelta(seconds=s), 24.7940, 120.9950) for s in (0, 5)] +
                   [(T0 - timedelta(seconds=30), 1.0, 1.0), (T0 + timedelta(seconds=999), 1.0, 1.0)],  # outside
            "amy": [(T0 + timedelta(seconds=8), 24.7945, 120.9950)],
        }
        data = build_replay(T0, T0 + timedelta(seconds=60), paths, "ben", TREASURE)
        self.assertEqual(data["duration_s"], 60)
        self.assertEqual([p["name"] for p in data["players"]], ["ben", "amy", "zed"])  # winner first, then names
        self.assertEqual([p["slot"] for p in data["players"]], [1, 2, 3])
        ben = data["players"][0]
        self.assertEqual(ben["points"][-1], [60, TREASURE["lat"], TREASURE["lon"]])  # ends on the treasure
        self.assertEqual(len(ben["points"]), 3)  # the two points outside the race are gone
        self.assertTrue(ben["winner"])
        self.assertIn("ben won", ben["summary"])
        self.assertEqual(data["headline"], "ben won the race in 1:00.")
        self.assertEqual(data["players"][1]["walked_m"], 0)

    def test_a_point_just_before_the_finish_is_kept(self):
        # The race lasted 30.45 s: a point at 30.4 s must not count as "after the finish".
        paths = {"amy": [(T0 + timedelta(seconds=30.4), 24.79, 120.99)]}
        data = build_replay(T0, T0 + timedelta(seconds=30.45), paths, None, TREASURE)
        self.assertEqual(data["duration_s"], 31)
        self.assertEqual(len(data["players"]), 1)

    def test_more_than_eight_players_are_grey(self):
        paths = {f"p{i}": [(T0, 24.79, 120.99)] for i in range(10)}
        slots = [p["slot"] for p in build_replay(T0, T0 + timedelta(seconds=9), paths, None, TREASURE)["players"]]
        self.assertEqual(slots, [1, 2, 3, 4, 5, 6, 7, 8, None, None])

    def test_headline_and_problems(self):
        self.assertIn("Nobody's path", headline("x", 10, 0))
        self.assertIn("nobody won", headline(None, 10, 2))
        self.assertIn("Only players", replay_problem(True, False))
        self.assertIn("once someone wins", replay_problem(False, True))
        self.assertIsNone(replay_problem(True, True))


class ReplayApiTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app("sqlite:///:memory:")
        self.ctx = self.app.app_context()
        self.ctx.push()
        self.ann, self.bob, self.eve = self.client("ann"), self.client("bob"), self.client("eve")
        self.hunt = Hunt(name="Race", capacity=2)
        db.session.add(self.hunt)
        db.session.flush()
        for name in ("ann", "bob"):
            db.session.add(HuntMember(hunt_id=self.hunt.id, user_id=self.uid(name)))
        self.treasure = db.session.execute(db.select(Treasure)).scalars().first()
        self.game = HuntGame(hunt_id=self.hunt.id, treasure_id=self.treasure.id,
                             started_at=_utc_now() - timedelta(seconds=30))
        db.session.add(self.game)
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        self.ctx.pop()

    def client(self, name):
        c = self.app.test_client()
        c.post("/api/register", json={"username": name, "password": "secret1"})
        return c

    def uid(self, name):
        return db.session.execute(db.select(User.id).filter_by(username=name)).scalar_one()

    def points(self, name):
        return db.session.query(RacePoint).filter_by(user_id=self.uid(name)).count()

    def test_positions_are_kept_while_racing_only_for_players(self):
        self.ann.post("/api/me/position", json={"lat": 24.7951, "lon": 120.9951})
        self.ann.post("/api/me/position", json={"lat": 24.7952, "lon": 120.9951})  # too soon: skipped
        self.eve.post("/api/me/position", json={"lat": 24.7952, "lon": 120.9951})  # not in the hunt
        self.assertEqual(self.points("ann"), 1)
        self.assertEqual(self.points("eve"), 0)

    def test_the_waiting_line_is_not_recorded(self):
        db.session.add(HuntMember(hunt_id=self.hunt.id, user_id=self.uid("eve")))  # 3rd in a 2-place hunt
        db.session.commit()
        self.eve.post("/api/me/position", json={"lat": 24.7952, "lon": 120.9951})
        self.assertEqual(self.points("eve"), 0)

    def test_nothing_is_recorded_before_the_start_or_after_the_win(self):
        self.game.started_at = None
        db.session.commit()
        self.ann.post("/api/me/position", json={"lat": 24.7951, "lon": 120.9951})
        self.game.started_at = _utc_now() - timedelta(seconds=30)
        self.game.winner_id = self.uid("bob")
        db.session.commit()
        self.ann.post("/api/me/position", json={"lat": 24.7951, "lon": 120.9951})
        self.assertEqual(self.points("ann"), 0)

    def test_watching_the_replay(self):
        self.ann.post("/api/me/position", json={"lat": 24.7951, "lon": 120.9951})
        self.assertEqual(self.ann.get(f"/api/hunts/{self.hunt.id}/replay").status_code, 409)  # not finished
        self.game.winner_id = self.uid("bob")
        self.game.finished_at = _utc_now()
        db.session.commit()
        data = self.ann.get(f"/api/hunts/{self.hunt.id}/replay").get_json()
        self.assertEqual(data["winner"], "bob")
        self.assertEqual([p["name"] for p in data["players"]], ["bob", "ann"])  # bob's path is just the finish
        self.assertEqual(data["hunt"]["name"], "Race")
        self.assertEqual(self.eve.get(f"/api/hunts/{self.hunt.id}/replay").status_code, 403)
        self.assertEqual(self.app.test_client().get(f"/api/hunts/{self.hunt.id}/replay").status_code, 401)
        self.assertEqual(self.ann.get("/api/hunts/999/replay").status_code, 404)

    def test_the_page(self):
        html = self.ann.get(f"/hunts/{self.hunt.id}/replay").get_data(as_text=True)
        self.assertIn('id="replayMap"', html)
        self.assertNotIn("innerHTML", html)
        self.assertEqual(self.app.test_client().get(f"/hunts/{self.hunt.id}/replay").status_code, 302)

    def test_the_demo_replay_link(self):
        self.assertEqual(self.ann.get("/hunts/demo-replay").headers["Location"], "/hunts")
        from demo_data import seed_demo_story
        seed_demo_story()
        demo = db.session.execute(db.select(Hunt.id).filter_by(name="Pond sprint (demo)")).scalar_one()
        self.assertEqual(self.ann.get("/hunts/demo-replay").headers["Location"], f"/hunts/{demo}/replay")

    def test_the_winners_notification_opens_the_replay(self):
        from notify_rules import HUNT_WON, link
        self.assertEqual(link(HUNT_WON, hunt_id=7), "/hunts/7/replay")
        self.assertEqual(link(HUNT_WON), "/hunts")


if __name__ == "__main__":
    unittest.main()

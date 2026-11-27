"""B: demo data for the six new ways to play (demo_play.py), and playing them like on stage."""

import unittest
from unittest.mock import patch

import box_code
from app import create_app
from demo_content import DEMO_PASSWORD
from demo_data import seed_demo_story
from demo_extras import seed_demo_extras
from demo_play import BOX_TREASURE, DEMO_TRAVELER, TEAM_TREASURE
from demo_reset import reset_demo
from location import haversine_m
from models import TeamLock, Traveler, TravelerMove, Treasure, TreasureBox, db
from treasure_input import MIN_TREASURE_GAP_M


class DemoPlayTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app("sqlite:///:memory:")
        self.ctx = self.app.app_context()
        self.ctx.push()
        self.added = seed_demo_story()["extras"]

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
        self.ctx.pop()

    def login(self, name):
        client = self.app.test_client()
        self.assertEqual(client.post("/api/login", json={"username": name, "password": DEMO_PASSWORD}).status_code, 200)
        return client

    def treasure(self, name):
        return db.session.execute(db.select(Treasure).filter_by(name=name)).scalar_one()

    def test_everything_is_there_once(self):
        self.assertIn(f"traveler {DEMO_TRAVELER['name']}", self.added)
        self.assertIn(f"team treasure {TEAM_TREASURE['name']}", self.added)
        self.assertIn(f"box treasure {BOX_TREASURE['name']}", self.added)
        counts = [db.session.query(m).count() for m in (Traveler, TravelerMove, TeamLock, TreasureBox, Treasure)]
        self.assertEqual(seed_demo_extras(), [])
        self.assertEqual(counts, [db.session.query(m).count() for m in (Traveler, TravelerMove, TeamLock, TreasureBox, Treasure)])

    def test_new_treasures_keep_their_distance(self):
        others = db.session.execute(db.select(Treasure)).scalars().all()
        for spec in (TEAM_TREASURE, BOX_TREASURE):
            for t in others:
                if t.name != spec["name"]:
                    self.assertGreaterEqual(haversine_m(spec["lat"], spec["lon"], t.lat, t.lon), MIN_TREASURE_GAP_M, t.name)

    def test_the_stage_story(self):
        player = self.login("demo_player")
        duck = player.get("/api/travelers").get_json()["travelers"][0]
        self.assertEqual(duck["where"], "At Cafe corner")
        cafe, library = self.treasure("Cafe corner"), self.treasure("Library steps")
        player.post(f"/api/travelers/{duck['id']}/pick", json={"lat": cafe.lat, "lon": cafe.lon})
        done = player.post(f"/api/travelers/{duck['id']}/drop", json={"lat": library.lat, "lon": library.lon}).get_json()
        self.assertEqual(done["coins_earned"], 25)

        team = self.treasure(TEAM_TREASURE["name"])
        lock = player.get("/api/team-locks").get_json()["locks"][0]
        spot = {"lat": team.lat, "lon": team.lon}
        self.assertFalse(player.post(f"/api/team-locks/{lock['id']}/here", json=spot).get_json()["opened"])
        self.assertTrue(self.login("alice").post(f"/api/team-locks/{lock['id']}/here", json=spot).get_json()["opened"])

        box = self.treasure(BOX_TREASURE["name"])
        secret = db.session.execute(db.select(TreasureBox.secret).filter_by(treasure_id=box.id)).scalar_one()
        with patch("box_api._now", return_value=1_795_716_000):
            proof = player.post(f"/api/treasures/{box.id}/box/proof", json={"code": box_code.code_at(secret, 1_795_716_000)})
        self.assertEqual(proof.status_code, 200)

    def test_a_reset_starts_the_story_again(self):
        player = self.login("demo_player")
        duck = player.get("/api/travelers").get_json()["travelers"][0]
        cafe = self.treasure("Cafe corner")
        player.post(f"/api/travelers/{duck['id']}/pick", json={"lat": cafe.lat, "lon": cafe.lon})
        reset_demo()
        again = self.login("demo_player").get("/api/travelers").get_json()["travelers"]
        self.assertEqual([t["where"] for t in again], ["At Cafe corner"])
        self.assertEqual(db.session.query(TeamLock).count(), 1)
        self.assertEqual(db.session.query(TreasureBox).count(), 1)


if __name__ == "__main__":
    unittest.main()


class SimulateBoxTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app("sqlite:///:memory:")
        with self.app.app_context():
            seed_demo_story()
            self.secret = db.session.execute(db.select(TreasureBox.secret)).scalar_one()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()
            db.engine.dispose()

    def run_box(self, argv, env=None):
        import os
        from simulate_box import main
        lines = []
        with patch.dict(os.environ, env or {}, clear=False):
            if env is None:
                os.environ.pop("BOX_SECRET", None)
            code = main(argv, say=lines.append, flask_app=self.app, clock=lambda: 1_795_716_000,
                        sleep=lambda s: None, ticks=3)
        return code, lines

    def test_list_and_show(self):
        code, lines = self.run_box(["--list"])
        self.assertEqual(code, 0)
        self.assertIn(BOX_TREASURE["name"], lines[0])
        code, lines = self.run_box([BOX_TREASURE["name"]])
        shown = box_code.code_at(self.secret, 1_795_716_000)
        self.assertIn(f"{shown[:3]} {shown[3:]}", lines[1])
        self.assertEqual(len(lines), 2)  # the same second: printed once
        self.assertNotIn(self.secret, " ".join(lines))  # the secret itself never shows

    def test_unknown_treasure_and_env_secret(self):
        self.assertEqual(self.run_box(["Nowhere"])[0], 1)
        code, lines = self.run_box([], env={"BOX_SECRET": self.secret})
        self.assertEqual(code, 0)
        self.assertIn(box_code.code_at(self.secret, 1_795_716_000)[:3], lines[1])

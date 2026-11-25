"""B: a trail's shape (loop back, or one way to the last treasure) and skipping low-rated treasures."""

import os
import unittest
from unittest.mock import patch

import requests

from app import create_app
from models import Treasure, TreasureRating, User, db
from trail_planner import low_rated, parse_active_trail, parse_shape, path_length, plan_trail, trail_post_text

HOME = (24.7955, 120.9965)
D = 0.001  # about 111 m of latitude


def line():
    """Three treasures in a straight line going north."""
    return [{"id": i, "lat": HOME[0] + i * D, "lon": HOME[1]} for i in (1, 2, 3)]


class RulesTest(unittest.TestCase):
    def test_parse_shape(self):
        self.assertEqual(parse_shape(None), "loop")
        self.assertEqual(parse_shape("oneway"), "oneway")
        with self.assertRaises(ValueError):
            parse_shape("zigzag")

    def test_one_way_is_shorter(self):
        pts = [(t["lat"], t["lon"]) for t in line()]
        self.assertAlmostEqual(path_length(HOME, pts, loop=True), 2 * path_length(HOME, pts, loop=False), delta=1)

    def test_one_way_reaches_further(self):
        budget = 3.5 * 111 * 1.3  # enough for 3 treasures one way, not there and back
        self.assertEqual(plan_trail(HOME, line(), budget, loop=False)["ids"], [1, 2, 3])
        self.assertEqual(plan_trail(HOME, line(), budget, loop=True)["ids"], [1])

    def test_low_rated(self):
        ratings = {1: [1, 2], 2: [1], 3: [2, 5], 4: [2, 2, 2]}
        self.assertEqual(low_rated(ratings), {1, 4})  # 2 has one rating only; 3 averages 3.5

    def test_one_way_post_text(self):
        self.assertIn("one-way Treasure Trail", trail_post_text(2, 800, 600, 1000, 40, shape="oneway"))

    def test_active_trail_keeps_shape(self):
        state = {"checkpoints": [{"lat": HOME[0], "lon": HOME[1], "name": "Pond", "label": 1, "id": 3}],
                 "index": 0, "start": list(HOME), "meters": 0, "elapsed_s": 0, "shape": "oneway"}
        self.assertEqual(parse_active_trail(state)["shape"], "oneway")  # one checkpoint is fine one way


class ApiTest(unittest.TestCase):
    def setUp(self):
        env = patch.dict(os.environ, {}, clear=False)
        env.start()
        os.environ.pop("ORS_API_KEY", None)  # straight lines, never the real route service
        self.addCleanup(env.stop)
        self.app = create_app("sqlite:///:memory:")
        self.context = self.app.app_context()
        self.context.push()
        self.client = self.app.test_client()
        db.session.execute(db.delete(Treasure))  # only this test's treasures
        for t in line():
            db.session.add(Treasure(id=t["id"], name=f"T{t['id']}", lat=t["lat"], lon=t["lon"]))
        db.session.commit()
        self.client.post("/api/register", json={"username": "ann", "password": "secret1"})

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
        self.context.pop()

    def plan(self, **extra):
        return self.client.post("/api/trail", json={"lat": HOME[0], "lon": HOME[1], "steps": 1000, **extra})

    def test_bad_options(self):
        self.assertEqual(self.plan(shape="zigzag").status_code, 400)
        self.assertEqual(self.plan(skip_low="yes").status_code, 400)

    @patch("routing.requests.post", side_effect=requests.ConnectionError)
    def test_one_way_does_not_come_back(self, _):
        loop = self.plan().get_json()
        oneway = self.plan(shape="oneway").get_json()
        self.assertEqual((loop["shape"], oneway["shape"]), ("loop", "oneway"))
        self.assertGreater(len(oneway["stops"]), len(loop["stops"]))
        self.assertEqual(loop["path"][-1], list(HOME))           # back where you started
        self.assertNotEqual(oneway["path"][-1], list(HOME))      # ends at the last treasure
        self.assertIn("one-way trail", oneway["message"])

    @patch("routing.requests.post", side_effect=requests.ConnectionError)
    def test_skip_low_rated(self, _):
        for n, stars in enumerate((1, 2), start=1):
            self.client.post("/api/register", json={"username": f"rater{n}", "password": "secret1"})
            rater = db.session.execute(db.select(User).filter_by(username=f"rater{n}")).scalar_one()
            db.session.add(TreasureRating(user_id=rater.id, treasure_id=1, stars=stars))
        db.session.commit()
        self.client.post("/api/login", json={"username": "ann", "password": "secret1"})
        data = self.plan(shape="oneway", skip_low=True).get_json()
        self.assertNotIn(1, [s["id"] for s in data["stops"]])
        self.assertIn("Skipped 1 low-rated treasure", data["message"])
        self.assertIn(1, [s["id"] for s in self.plan(shape="oneway").get_json()["stops"]])

    def test_one_way_finish_is_at_the_last_checkpoint(self):
        last = [HOME[0] + 3 * D, HOME[1]]
        body = {"distance_m": 450, "duration_s": 400, "lat": last[0], "lon": last[1], "end": last,
                "shape": "oneway", "checkpoints": 3}
        res = self.client.post("/api/trail/walks", json=body)
        self.assertEqual(res.status_code, 201)
        self.assertIn("one-way", res.get_json()["text"])
        far = self.client.post("/api/trail/walks", json=body | {"lat": HOME[0], "lon": HOME[1]})
        self.assertIn("last checkpoint", far.get_json()["error"])

    def test_the_map_has_the_choices(self):
        html = self.client.get("/").get_data(as_text=True)
        for part in ('data-shape="loop"', 'data-shape="oneway"', 'id="trailSkipLow"', "shape: trailShape"):
            self.assertIn(part, html)


if __name__ == "__main__":
    unittest.main()

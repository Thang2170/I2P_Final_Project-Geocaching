"""B: trail history (/trails) and personal bests on the same trail."""

import unittest

from app import create_app
from models import TrailWalk, TrailWalkDetail, Treasure, db
from trail_planner import best_change, best_text, pace_text, trail_signature

HOME = [24.7955, 120.9965]


class RulesTest(unittest.TestCase):
    def test_signature(self):
        self.assertEqual(trail_signature("loop", [7, 3, 12]), "loop:3-7-12")
        self.assertEqual(trail_signature("loop", [12, 3, 7]), trail_signature("loop", [3, 7, 12]))  # any order
        self.assertNotEqual(trail_signature("oneway", [3, 7]), trail_signature("loop", [3, 7]))
        self.assertIsNone(trail_signature("loop", []))

    def test_best_change(self):
        self.assertEqual(best_change(None, 600)["first_time"], True)
        better = best_change(600, 540)
        self.assertEqual((better["personal_best"], better["faster_by_s"]), (True, 60))
        self.assertFalse(best_change(600, 600)["personal_best"])  # a tie is not a new best
        self.assertEqual(best_change(600, 700)["faster_by_s"], 0)
        self.assertIn("1:00 faster", best_text(better))
        self.assertEqual(best_text(best_change(None, 600)), "")  # nothing to brag about the first time

    def test_pace(self):
        self.assertEqual(pace_text(1000, 600), "10:00 /km")
        self.assertEqual(pace_text(5, 60), "–")


class ApiTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app("sqlite:///:memory:")
        self.context = self.app.app_context()
        self.context.push()
        self.client = self.app.test_client()
        self.client.post("/api/register", json={"username": "ann", "password": "secret1"})
        for i, name in ((3, "Pond"), (7, "Library")):
            db.session.add(Treasure(id=i, name=name, lat=HOME[0], lon=HOME[1]))
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
        self.context.pop()

    def walk(self, duration_s, ids=(7, 3), **extra):
        body = {"distance_m": 1000, "duration_s": duration_s, "lat": HOME[0], "lon": HOME[1], "end": HOME,
                "checkpoints": len(ids), "treasure_ids": list(ids), "splits": [duration_s // 2, duration_s]}
        return self.client.post("/api/trail/walks", json={**body, **extra})

    def test_must_log_in(self):
        self.assertEqual(self.app.test_client().get("/api/trail/walks").status_code, 401)

    def test_bad_treasure_ids(self):
        for bad in ("7", [0], [True], ["x"], list(range(1, 30))):
            self.assertEqual(self.walk(600, treasure_ids=bad).status_code, 400, bad)

    def test_personal_bests(self):
        first = self.walk(700).get_json()
        self.assertTrue(first["best"]["first_time"])
        self.assertNotIn("personal best", first["text"])
        slower = self.walk(760, ids=(3, 7)).get_json()  # same treasures, other order: same trail
        self.assertFalse(slower["best"]["personal_best"])
        faster = self.walk(640).get_json()
        self.assertEqual((faster["best"]["personal_best"], faster["best"]["faster_by_s"]), (True, 60))
        self.assertIn("New personal best, 1:00 faster", faster["text"])
        other = self.walk(500, ids=(3,)).get_json()  # a different trail starts its own bests
        self.assertTrue(other["best"]["first_time"])

        walks = self.client.get("/api/trail/walks").get_json()
        self.assertEqual(walks["totals"]["walks"], 4)
        by_time = {w["duration"]: w for w in walks["walks"]}
        self.assertTrue(by_time["10:40"]["personal_best"])
        self.assertFalse(by_time["11:40"]["personal_best"])
        self.assertFalse(by_time["8:20"]["personal_best"])  # walked once: nothing to beat yet
        self.assertEqual((by_time["10:40"]["times_walked"], by_time["10:40"]["best"]), (3, "10:40"))
        self.assertEqual(by_time["10:40"]["treasures"], ["Library", "Pond"])
        self.assertEqual(by_time["10:40"]["splits"], "1 at 5:20 · finish 10:40")
        self.assertEqual(walks["walks"][0]["duration"], "8:20")  # newest first

    def test_older_walk_without_details(self):
        db.session.add(TrailWalk(user_id=1, checkpoints=2, distance_m=900, duration_s=600, steps=1200, calories=40))
        db.session.commit()
        walks = self.client.get("/api/trail/walks").get_json()["walks"]
        self.assertEqual((walks[0]["shape"], walks[0]["treasures"], walks[0]["personal_best"]), ("loop", [], False))

    def test_pages(self):
        html = self.client.get("/trails").get_data(as_text=True)
        self.assertIn("My trails", html)
        self.assertIn("/api/trail/walks", html)
        self.assertNotIn("innerHTML", html)
        self.assertIn('href="/trails"', self.client.get("/").get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()


class WalkAgainTest(unittest.TestCase):
    """B: ↻ Walk it again: found treasures never come back in a planned trail, so without this
    a personal best could never be beaten."""

    def setUp(self):
        self.app = create_app("sqlite:///:memory:")
        self.context = self.app.app_context()
        self.context.push()
        self.client = self.app.test_client()
        self.client.post("/api/register", json={"username": "ann", "password": "secret1"})
        for i, name in ((3, "Pond"), (7, "Library")):
            db.session.add(Treasure(id=i, name=name, lat=HOME[0] + i * 0.0001, lon=HOME[1]))
        db.session.commit()
        body = {"distance_m": 1000, "duration_s": 600, "lat": HOME[0], "lon": HOME[1], "end": HOME,
                "checkpoints": 2, "treasure_ids": [7, 3], "shape": "loop"}
        self.walk_id = self.client.post("/api/trail/walks", json=body).get_json()["id"]

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
        self.context.pop()

    def again(self, walk_id=None, lat=HOME[0], lon=HOME[1]):
        return self.client.get(f"/api/trail/walks/{walk_id or self.walk_id}/again?lat={lat}&lon={lon}")

    def test_same_treasures_same_order(self):
        data = self.again(lat=24.8).get_json()
        self.assertEqual([s["id"] for s in data["stops"]], [7, 3])
        self.assertEqual((data["shape"], data["start"]), ("loop", [24.8, HOME[1]]))  # from where you are now

    def test_only_your_own_trails(self):
        self.assertEqual(self.again(walk_id=999).status_code, 404)
        self.client.post("/api/register", json={"username": "bob", "password": "secret1"})  # now logged in as bob
        self.assertEqual(self.again().status_code, 404)

    def test_removed_treasures(self):
        db.session.delete(db.session.get(Treasure, 3))
        db.session.commit()
        data = self.again().get_json()
        self.assertEqual([s["id"] for s in data["stops"]], [7])
        self.assertIn("1 treasure was removed", data["message"])
        db.session.delete(db.session.get(Treasure, 7))
        db.session.commit()
        self.assertEqual(self.again().status_code, 400)

    def test_bad_position(self):
        self.assertEqual(self.again(lat="x").status_code, 400)

    def test_pages_have_it(self):
        self.assertIn("Walk it again", self.client.get("/trails").get_data(as_text=True))
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn("function walkAgain()", html)
        self.assertIn('params.get("trail")', html)

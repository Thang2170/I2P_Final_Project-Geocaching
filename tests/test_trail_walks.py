"""B: walking a Treasure Trail with the live panel (time, pace, splits), saved and posted at the finish."""

import unittest

from app import create_app
from models import Post, TrailWalk, User, db
from trail_planner import fmt_duration, splits_text, trail_post_text

HOME = [24.7955, 120.9965]


class TextRulesTest(unittest.TestCase):
    def test_durations(self):
        self.assertEqual(fmt_duration(65), "1:05")
        self.assertEqual(fmt_duration(1450), "24:10")
        self.assertEqual(fmt_duration(4000), "1:06:40")

    def test_splits(self):
        self.assertEqual(splits_text([185, 460, 751]), "1 at 3:05 · 2 at 7:40 · 🏁 12:31")
        self.assertEqual(splits_text([]), "")

    def test_post_text(self):
        text = trail_post_text(3, 2140, 1450, 2850, 131.6, [300, 700, 1100, 1450])
        self.assertIn("3 checkpoints, 2.14 km in 24:10", text)
        self.assertIn("(11:17 /km)", text)
        self.assertIn("2,850 steps, 132 kcal", text)
        self.assertIn("🏁 24:10", text)
        self.assertIn("1 checkpoint,", trail_post_text(1, 500, 300, 600, 20))


class SaveWalkTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app("sqlite:///:memory:")
        self.context = self.app.app_context()
        self.context.push()
        self.client = self.app.test_client()
        self.client.post("/api/register", json={"username": "ann", "password": "secret1"})

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
        self.context.pop()

    def save(self, **change):
        body = {"distance_m": 2140, "duration_s": 1450, "lat": HOME[0], "lon": HOME[1], "start": HOME,
                "checkpoints": 3, "splits": [300, 700, 1100, 1450]}
        return self.client.post("/api/trail/walks", json={**body, **change})

    def test_must_log_in(self):
        self.assertEqual(self.app.test_client().post("/api/trail/walks", json={}).status_code, 401)

    def test_saved_and_posted(self):
        res = self.save()
        self.assertEqual(res.status_code, 201)
        data = res.get_json()
        walk = db.session.get(TrailWalk, data["id"])
        self.assertEqual((walk.checkpoints, walk.duration_s), (3, 1450))
        self.assertGreater(walk.steps, 2000)  # Python's steps, not the browser's
        post = db.session.get(Post, data["post_id"])
        self.assertIn("Treasure Trail", post.text)
        self.assertIn("Treasure Trail", self.client.get("/api/feed").get_data(as_text=True))

    def test_must_be_back_at_the_start(self):
        res = self.save(lat=HOME[0] + 0.002)
        self.assertEqual(res.status_code, 400)
        self.assertIn("from the start", res.get_json()["error"])

    def test_too_fast_is_refused(self):
        res = self.save(distance_m=9000, duration_s=600)  # 54 km/h
        self.assertEqual(res.status_code, 400)
        self.assertEqual(db.session.execute(db.select(db.func.count()).select_from(TrailWalk)).scalar(), 0)

    def test_bad_input(self):
        for change in ({"checkpoints": 0}, {"checkpoints": "3"}, {"start": [1]}, {"splits": [500, 100]},
                       {"splits": [99999]}, {"splits": list(range(25))}, {"duration_s": 0}, {"lat": "x"}):
            self.assertEqual(self.save(**change).status_code, 400, change)

    def test_no_splits_is_fine(self):
        self.assertEqual(self.save(splits=[]).status_code, 201)


class MapPageTest(unittest.TestCase):
    def test_trail_journey_on_the_map(self):
        app = create_app("sqlite:///:memory:")
        client = app.test_client()
        client.post("/api/register", json={"username": "ann", "password": "secret1"})
        html = client.get("/").get_data(as_text=True)
        for part in ('id="trailStartBtn"', 'kind: "trail"', "/api/trail/walks", "function finishTrailWalk(",
                     "claimCoins(cp.id, cp.name, lat, lon)", "journey.splits.push"):
            self.assertIn(part, html)


if __name__ == "__main__":
    unittest.main()

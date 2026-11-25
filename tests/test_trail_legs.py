"""B: a Treasure Trail is walked one leg at a time: the map shows only the next checkpoint and
the route to it, and Python decides when you reached it (trail_planner.trail_progress)."""

import unittest

from app import create_app
from trail_planner import trail_progress

HOME = (24.7955, 120.9965)
D = 0.001  # about 111 m of latitude here
STOPS = [(HOME[0] + D, HOME[1]), (HOME[0] + D, HOME[1] + D), HOME]  # two stops, then back home


class ProgressRuleTest(unittest.TestCase):
    def test_far_away(self):
        result = trail_progress(HOME, STOPS, 0, 20)
        self.assertEqual((result["index"], result["reached"], result["done"]), (0, 0, False))
        self.assertAlmostEqual(result["meters"], 111, delta=2)

    def test_reaching_a_checkpoint(self):
        near = (STOPS[0][0] + 0.0001, STOPS[0][1])  # about 11 m away
        result = trail_progress(near, STOPS, 0, 20)
        self.assertEqual((result["index"], result["reached"]), (1, 1))
        self.assertAlmostEqual(result["meters"], 101, delta=3)

    def test_last_checkpoint_finishes(self):
        result = trail_progress(HOME, STOPS, 2, 20)
        self.assertEqual((result["index"], result["meters"], result["done"]), (3, None, True))

    def test_checkpoints_on_the_same_spot_are_ticked_together(self):
        same = [(HOME[0] + D, HOME[1])] * 2 + [HOME]
        self.assertEqual(trail_progress(same[0], same, 0, 20)["index"], 2)

    def test_bad_index(self):
        for bad in (-1, 4):
            with self.assertRaises(ValueError):
                trail_progress(HOME, STOPS, bad, 20)


class ProgressApiTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app("sqlite:///:memory:")
        self.client = self.app.test_client()

    def ask(self, **body):
        base = {"lat": STOPS[0][0], "lon": STOPS[0][1], "index": 0, "checkpoints": [list(p) for p in STOPS]}
        return self.client.post("/api/trail/progress", json={**base, **body})

    def test_progress(self):
        data = self.ask().get_json()
        self.assertEqual((data["index"], data["reached"], data["done"]), (1, 1, False))

    def test_bad_input(self):
        self.assertEqual(self.ask(index="0").status_code, 400)
        self.assertEqual(self.ask(index=True).status_code, 400)
        self.assertEqual(self.ask(index=9).status_code, 400)
        self.assertEqual(self.ask(checkpoints=[]).status_code, 400)
        self.assertEqual(self.ask(checkpoints=[[1, 2, 3]]).status_code, 400)
        self.assertEqual(self.ask(checkpoints=[[95, 0]]).status_code, 400)
        self.assertEqual(self.ask(lat="x").status_code, 400)

    def test_trail_answer_has_the_start(self):
        self.client.post("/api/register", json={"username": "ann", "password": "secret1"})
        data = self.client.post("/api/trail", json={"lat": HOME[0], "lon": HOME[1], "steps": 3000}).get_json()
        self.assertTrue(data["stops"])  # the app's starting treasure is nearby
        self.assertEqual(data["start"], [HOME[0], HOME[1]])  # the last checkpoint is back here


class MapPageTest(unittest.TestCase):
    def setUp(self):
        app = create_app("sqlite:///:memory:")
        client = app.test_client()
        client.post("/api/register", json={"username": "ann", "password": "secret1"})
        self.html = client.get("/").get_data(as_text=True)
        self.css = client.get("/static/css/app.css").get_data(as_text=True)

    def test_trail_is_walked_leg_by_leg(self):
        self.assertIn("/api/trail/progress", self.html)
        self.assertIn("function drawTrailLeg(", self.html)
        self.assertIn("checkTrail(lat, lon)", self.html)
        self.assertNotIn("data.stops.map(stop => L.marker", self.html)  # no longer every stop at once

    def test_compact_status_card(self):
        self.assertIn('id="sheetMoreBtn"', self.html)
        self.assertIn('id="sheetMore" class="sheet__more" hidden', self.html)
        more = self.html.split('id="sheetMore"', 1)[1].split("</section>", 1)[0]
        for part in ('id="coinInfo"', 'id="modePicker"', 'id="crossingInfo"'):
            self.assertIn(part, more)  # folded away under "More"
        self.assertIn("max-height: 34vh", self.css)


if __name__ == "__main__":
    unittest.main()


class ShowAllCheckpointsTest(unittest.TestCase):
    """B: a box on the map shows or hides the other checkpoints; their routes are never drawn."""

    def setUp(self):
        app = create_app("sqlite:///:memory:")
        client = app.test_client()
        client.post("/api/register", json={"username": "ann", "password": "secret1"})
        self.html = client.get("/").get_data(as_text=True)
        self.css = client.get("/static/css/app.css").get_data(as_text=True)

    def test_the_box(self):
        self.assertIn('id="trailToggle" class="trail-toggle" hidden', self.html)
        self.assertIn('<input type="checkbox" id="trailShowAll">', self.html)
        self.assertIn(".trail-toggle {", self.css)

    def test_other_checkpoints_are_pins_only(self):
        start = self.html.index("function drawTrailOthers()")
        body = self.html[start:self.html.index("trailShowAll.addEventListener", start)]
        self.assertIn("L.marker(", body)
        self.assertNotIn("polyline", body)  # no route to them
        self.assertIn("i === trail.index ? null", body)  # the next one is drawn with its route already

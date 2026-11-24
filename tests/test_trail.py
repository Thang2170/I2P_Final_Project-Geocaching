"""Treasure Trail: a walking loop through unfound treasures (trail_planner.py, trail_api.py, map.html)."""

import unittest
from unittest.mock import patch

from app import create_app
from models import Treasure, User, db
from trail_planner import (MAX_STOPS, WALK_FACTOR, loop_length, parse_goal, plan_trail, two_opt,
                           walk_m)

HOME = (24.7955, 120.9965)
D = 0.001  # about 111 m of latitude here


def square():
    """Four treasures on the corners of a square next to HOME, listed in a crossing order."""
    return [{"id": 1, "lat": HOME[0] + D, "lon": HOME[1]},
            {"id": 2, "lat": HOME[0], "lon": HOME[1] + D},
            {"id": 3, "lat": HOME[0] + D, "lon": HOME[1] + D},
            {"id": 4, "lat": HOME[0] + 2 * D, "lon": HOME[1] + D}]


class TestGoal(unittest.TestCase):
    def test_steps_and_minutes(self):
        self.assertEqual(parse_goal({"steps": 3000}), (2250.0, "3,000 steps"))   # 0.75 m a step
        self.assertEqual(parse_goal({"minutes": 20}), (1680.0, "20 min"))        # 1.4 m/s

    def test_bad_goals(self):
        for data in ({}, {"steps": 3000, "minutes": 20}, {"steps": 100}, {"minutes": 999},
                     {"steps": "3000"}, {"steps": 2.5}, {"steps": True}, None):
            with self.subTest(data=data), self.assertRaises(ValueError):
                parse_goal(data)


class TestPlanner(unittest.TestCase):
    def test_walking_distance_is_longer_than_the_straight_line(self):
        self.assertAlmostEqual(walk_m(HOME, (HOME[0] + D, HOME[1])), 111.2 * WALK_FACTOR, delta=1)

    def test_two_opt_uncrosses_the_loop(self):
        corners = [(HOME[0] + D, HOME[1]), (HOME[0], HOME[1] + D), (HOME[0] + D, HOME[1] + D)]
        crossed = [corners[1], corners[0], corners[2]]  # goes back and forth
        better = two_opt(crossed, lambda pts: loop_length(HOME, pts))
        self.assertLess(loop_length(HOME, better), loop_length(HOME, crossed))

    def test_the_loop_fits_the_budget(self):
        for budget in (400, 700, 1200, 5000):
            with self.subTest(budget=budget):
                plan = plan_trail(HOME, square(), budget)
                self.assertLessEqual(plan["estimate_m"], budget)

    def test_a_bigger_budget_visits_more(self):
        counts = [len(plan_trail(HOME, square(), b)["ids"]) for b in (300, 700, 1200)]
        self.assertEqual(counts, sorted(counts))
        self.assertEqual(plan_trail(HOME, square(), 5000)["ids"].__len__(), 4)

    def test_nothing_fits(self):
        self.assertEqual(plan_trail(HOME, square(), 100), {"ids": [], "estimate_m": 0.0})
        self.assertEqual(plan_trail(HOME, [], 5000)["ids"], [])

    def test_the_order_does_not_cross_itself(self):
        plan = plan_trail(HOME, square(), 5000)
        points = {t["id"]: (t["lat"], t["lon"]) for t in square()}
        order = [points[i] for i in plan["ids"]]
        self.assertEqual(two_opt(order, lambda pts: loop_length(HOME, pts)), order)  # already the best 2-opt

    def test_at_most_eight_stops(self):
        many = [{"id": i, "lat": HOME[0] + D * (i % 5) / 4, "lon": HOME[1] + D * (i // 5) / 4} for i in range(1, 21)]
        self.assertEqual(len(plan_trail(HOME, many, 20_000)["ids"]), MAX_STOPS)

    def test_same_answer_every_time(self):
        self.assertEqual(plan_trail(HOME, square(), 900), plan_trail(HOME, list(reversed(square())), 900))


class TestTrailApi(unittest.TestCase):
    def setUp(self):
        self.app = create_app("sqlite:///:memory:")
        self.context = self.app.app_context()
        self.context.push()
        self.client = self.app.test_client()
        self.client.post("/api/register", json={"username": "ann", "password": "secret1"})
        self.ann = db.session.execute(db.select(User).filter_by(username="ann")).scalar_one()
        db.session.query(Treasure).delete()  # only the treasures this test adds
        for t in square():
            db.session.add(Treasure(id=t["id"], name=f"T{t['id']}", lat=t["lat"], lon=t["lon"]))
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
        self.context.pop()

    def trail(self, **goal):
        return self.client.post("/api/trail", json={"lat": HOME[0], "lon": HOME[1], **goal})

    def test_needs_login_and_a_goal(self):
        self.assertEqual(self.app.test_client().post("/api/trail", json={}).status_code, 401)
        self.assertEqual(self.trail().status_code, 400)
        self.assertEqual(self.client.post("/api/trail", json={"steps": 3000}).status_code, 400)

    def test_a_loop_through_the_treasures(self):
        with patch("routing.requests.post", side_effect=Exception("offline")):
            data = self.trail(steps=5000).get_json()
        self.assertEqual(len(data["stops"]), 4)
        self.assertEqual([s["order"] for s in data["stops"]], [1, 2, 3, 4])
        self.assertEqual(data["path"][0], data["path"][-1])  # back where you started
        self.assertEqual(data["path"][0], list(HOME))
        self.assertIn("straight lines", data["warning"])      # no routing key in tests
        self.assertGreater(data["steps"], 0)
        self.assertEqual(data["goal"], "5,000 steps")
        self.assertIn("every treasure you haven't found", data["message"])  # all 4 fit: say why it's short

    def test_found_and_own_treasures_are_left_out(self):
        self.client.post("/api/treasures/1/claim", json={"lat": HOME[0] + D, "lon": HOME[1]})
        db.session.get(Treasure, 2).created_by = self.ann.id
        db.session.commit()
        ids = [s["id"] for s in self.trail(steps=5000).get_json()["stops"]]
        self.assertEqual(sorted(ids), [3, 4])

    def test_too_short_a_walk(self):
        far = {"lat": HOME[0] - 5 * D, "lon": HOME[1]}  # about 550 m south of every treasure
        data = self.client.post("/api/trail", json={**far, "steps": 500}).get_json()  # a 375 m walk
        self.assertEqual(data["stops"], [])
        self.assertIn("Try a longer one", data["message"])


class TestMapPage(unittest.TestCase):
    def test_trail_controls(self):
        app = create_app("sqlite:///:memory:")
        client = app.test_client()
        client.post("/api/register", json={"username": "ann", "password": "secret1"})
        html = client.get("/").get_data(as_text=True)
        with app.app_context():
            db.session.remove()
            db.drop_all()
            db.engine.dispose()
        self.assertIn('id="trailBtn"', html)
        self.assertEqual(html.count('class="trail-pick"'), 6)
        self.assertIn('fetch("/api/trail"', html)
        self.assertIn("if (trailActive) return;", html)  # normal rerouting pauses during a trail
        self.assertIn("number.textContent", html)


if __name__ == "__main__":
    unittest.main()

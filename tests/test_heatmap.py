"""B: the campus heat map (heatmap.py, heatmap_api.py)."""

import unittest
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

from app import create_app
from heatmap import (DEFAULT_DAYS, KEEP_DAYS, LEVELS, MIN_PLAYERS, heat_cells, legend, level_of, parse_days,
                     place_text, summary_text, tip_text)
from models import HeatVisit, User, db
from territory import hex_of

SPOT = (24.7950, 120.9950)


class HeatRulesTest(unittest.TestCase):
    def test_parse_days(self):
        self.assertEqual(parse_days(None), DEFAULT_DAYS)
        self.assertEqual(parse_days("7"), 7)
        for bad in ("8", "abc", "-30"):
            with self.assertRaises(ValueError):
                parse_days(bad)

    def test_levels(self):
        self.assertEqual(level_of(MIN_PLAYERS - 1), 0)
        self.assertEqual(level_of(LEVELS[0]), 1)
        self.assertEqual(level_of(LEVELS[-1] + 100), 5)
        self.assertEqual([row["label"] for row in legend()][0], f"{LEVELS[0]}–{LEVELS[1] - 1} players")
        self.assertTrue(legend()[-1]["label"].endswith("+ players"))

    def test_a_spot_needs_five_different_players(self):
        busy = [(uid, 1, 2) for uid in range(MIN_PLAYERS)]
        lonely = [(99, 5, 5)] * 50  # one player walking back and forth all month: still one player
        cells = heat_cells(busy + busy + lonely)
        self.assertEqual([(c["q"], c["r"], c["players"]) for c in cells], [(1, 2, MIN_PLAYERS)])
        self.assertEqual(len(cells[0]["corners"]), 6)

    def test_busiest_first(self):
        visits = [(u, 0, 0) for u in range(5)] + [(u, 1, 0) for u in range(9)]
        self.assertEqual([c["players"] for c in heat_cells(visits)], [9, 5])

    def test_texts(self):
        self.assertIn("Not enough walkers", summary_text([], 30, 0))
        self.assertEqual(summary_text([{}], 7, 0), "1 busy spot in the last 7 days.")
        self.assertIn("3 quieter spots are hidden", summary_text([{}, {}], 30, 3))
        self.assertIn("1 quieter spot is hidden", summary_text([{}], 30, 1))
        self.assertEqual(tip_text({"players": 6}, 30, "Pond"), "6 players walked here near Pond in the last 30 days")
        self.assertEqual(place_text(None), "A spot with no treasure nearby")


class HeatApiTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app("sqlite:///:memory:")
        self.ctx = self.app.app_context()
        self.ctx.push()

    def tearDown(self):
        db.session.remove()
        self.ctx.pop()

    def walker(self, name, where=SPOT):
        c = self.app.test_client()
        c.post("/api/register", json={"username": name, "password": "secret1"})
        c.post("/api/me/position", json={"lat": where[0], "lon": where[1]})
        return c

    def test_needs_login(self):
        self.assertEqual(self.app.test_client().get("/api/heatmap").status_code, 401)
        self.assertEqual(self.app.test_client().get("/heatmap").status_code, 302)

    def test_positions_are_counted_once_a_day(self):
        ann = self.walker("ann")
        ann.post("/api/me/position", json={"lat": SPOT[0], "lon": SPOT[1]})
        self.assertEqual(db.session.query(HeatVisit).count(), 1)
        self.assertEqual((db.session.query(HeatVisit).one().q, db.session.query(HeatVisit).one().r), hex_of(*SPOT))

    def test_four_players_stay_hidden_five_show(self):
        clients = [self.walker(f"walker{i}") for i in range(MIN_PLAYERS - 1)]
        data = clients[0].get("/api/heatmap").get_json()
        self.assertEqual(data["cells"], [])
        self.assertIn("Not enough walkers", data["summary"])
        last = self.walker("walker_last")
        data = last.get("/api/heatmap?days=7").get_json()
        self.assertEqual(len(data["cells"]), 1)
        self.assertEqual(data["cells"][0]["players"], MIN_PLAYERS)
        self.assertEqual(data["days"], 7)
        self.assertIn("players walked here", data["cells"][0]["tip"])
        self.assertEqual(last.get("/api/heatmap?days=5").status_code, 400)

    def test_old_visits_drop_out_and_get_deleted(self):
        ann = self.walker("ann")
        uid = db.session.execute(db.select(User.id).filter_by(username="ann")).scalar_one()
        today = date.today()
        db.session.add(HeatVisit(user_id=uid, q=50, r=50, day=today - timedelta(days=KEEP_DAYS + 5)))
        db.session.add(HeatVisit(user_id=uid, q=51, r=51, day=today - timedelta(days=40)))
        db.session.commit()
        with patch("heatmap_api._now", return_value=datetime.now(timezone.utc)):
            ann.post("/api/me/position", json={"lat": SPOT[0] + 0.001, "lon": SPOT[1]})
        days = sorted(v.day for v in db.session.query(HeatVisit).filter_by(user_id=uid))
        self.assertNotIn(today - timedelta(days=KEEP_DAYS + 5), days)  # deleted
        self.assertIn(today - timedelta(days=40), days)                # kept (inside 90 days)

    def test_the_demo_has_a_heat_map(self):
        from demo_data import seed_demo_story
        seed_demo_story()
        c = self.app.test_client()
        c.post("/api/login", json={"username": "demo_player", "password": "demo1234"})
        data = c.get("/api/heatmap").get_json()
        self.assertGreaterEqual(len(data["cells"]), 5)
        self.assertGreaterEqual(max(cell["level"] for cell in data["cells"]), 2)
        self.assertIn("hidden to keep paths private", data["summary"])  # the two-player path stays hidden

    def test_the_page(self):
        html = self.walker("ann").get("/heatmap").get_data(as_text=True)
        self.assertIn('id="heatMap"', html)
        self.assertNotIn("innerHTML", html)


if __name__ == "__main__":
    unittest.main()

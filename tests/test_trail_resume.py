"""B: a timed Treasure Trail survives a reload: the server keeps its state for 30 minutes."""

import unittest
from datetime import datetime, timedelta, timezone

from app import create_app
from models import ActiveTrail, User, db
from trail_planner import TRAIL_RESUME_S, can_carry_on, parse_active_trail

CPS = [{"id": 3, "lat": 24.7965, "lon": 120.9965, "name": "Pond bench", "label": 1},
       {"id": None, "lat": 24.7955, "lon": 120.9965, "name": "back to the start", "label": "🏁"}]


def state(**change):
    base = {"checkpoints": CPS, "index": 1, "start": [24.7955, 120.9965], "splits": [95],
            "meters": 140, "elapsed_s": 130}
    return {**base, **change}


class RulesTest(unittest.TestCase):
    def test_clean_state(self):
        s = parse_active_trail(state())
        self.assertEqual((s["index"], s["splits"], s["meters"]), (1, [95], 140.0))
        self.assertEqual([c["label"] for c in s["checkpoints"]], ["1", "🏁"])
        self.assertIsNone(s["checkpoints"][1]["id"])

    def test_bad_state(self):
        bad = [None, state(checkpoints=CPS[:1]), state(checkpoints=[CPS[0], "x"]), state(index=2),
               state(index=True), state(start=[1]), state(splits=[100, 50]), state(splits=[999]),
               state(meters=-1), state(meters=float("nan")), state(elapsed_s=1.5),
               state(checkpoints=[CPS[0] | {"name": ""}, CPS[1]]), state(checkpoints=[CPS[0] | {"lat": 95}, CPS[1]]),
               state(checkpoints=[CPS[0] | {"id": "3"}, CPS[1]])]
        for data in bad:
            with self.assertRaises(ValueError, msg=data):
                parse_active_trail(data)

    def test_window(self):
        self.assertTrue(can_carry_on(0))
        self.assertTrue(can_carry_on(TRAIL_RESUME_S))
        self.assertFalse(can_carry_on(TRAIL_RESUME_S + 1))
        self.assertFalse(can_carry_on(-5))


class ApiTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app("sqlite:///:memory:")
        self.context = self.app.app_context()
        self.context.push()
        self.client = self.app.test_client()
        self.client.post("/api/register", json={"username": "ann", "password": "secret1"})
        self.ann = db.session.execute(db.select(User).filter_by(username="ann")).scalar_one()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
        self.context.pop()

    def test_must_log_in(self):
        other = self.app.test_client()
        self.assertEqual(other.get("/api/trail/active").status_code, 401)
        self.assertEqual(other.post("/api/trail/active", json=state()).status_code, 401)
        self.assertEqual(other.delete("/api/trail/active").status_code, 401)

    def test_keep_carry_on_and_end(self):
        self.assertIsNone(self.client.get("/api/trail/active").get_json()["active"])
        self.assertEqual(self.client.post("/api/trail/active", json=state()).status_code, 200)
        self.client.post("/api/trail/active", json=state(meters=300, elapsed_s=260, splits=[95, 250]))
        active = self.client.get("/api/trail/active").get_json()["active"]
        self.assertEqual((active["meters"], active["elapsed_s"], active["splits"]), (300, 260, [95, 250]))
        self.assertLessEqual(active["since_update_s"], 2)
        self.assertEqual(db.session.execute(db.select(db.func.count()).select_from(ActiveTrail)).scalar(), 1)
        self.client.delete("/api/trail/active")
        self.assertIsNone(self.client.get("/api/trail/active").get_json()["active"])

    def test_bad_state_is_refused(self):
        self.assertEqual(self.client.post("/api/trail/active", json=state(index=9)).status_code, 400)

    def test_stale_trail_is_forgotten(self):
        self.client.post("/api/trail/active", json=state())
        row = db.session.get(ActiveTrail, self.ann.id)
        row.updated_at = datetime.now(timezone.utc) - timedelta(minutes=31)
        db.session.commit()
        data = self.client.get("/api/trail/active").get_json()
        self.assertEqual((data["active"], data["expired"]), (None, True))
        self.assertIsNone(db.session.get(ActiveTrail, self.ann.id))

    def test_the_map_carries_trails_on(self):
        html = self.client.get("/").get_data(as_text=True)
        for part in ("resumeTrail();", "function keepTrail()", "function forgetTrail()", '"/api/trail/active"',
                     'if (journey.kind === "trail") forgetTrail();'):
            self.assertIn(part, html)


if __name__ == "__main__":
    unittest.main()

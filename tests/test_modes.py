"""B: walking modes (C's #6): try-hard (fast, big bonus) and calm walks (calm spots, mindful prompts)."""

import unittest
from datetime import date

from app import create_app
from models import CoinTransaction, ModeBonus, Treasure, User, db
from modes import (CALM_COINS, PROMPTS, TRYHARD_MAX, TRYHARD_MIN, calm_bonus, calm_kind, calm_prompt, calm_spot,
                   pace_status, parse_mode, tryhard_bonus)

LAT, LON = 24.795324, 120.994796


class RulesTest(unittest.TestCase):
    def test_parse_mode(self):
        self.assertEqual(parse_mode("calm"), "calm")
        for bad in ("fast", "", None):
            with self.assertRaises(ValueError):
                parse_mode(bad)

    def test_pace(self):
        self.assertIsNone(pace_status(10, 60)["on_pace"])
        on = pace_status(1000, 540)
        self.assertEqual((on["on_pace"], on["pace"], on["target"]), (True, "9:00", "10:00"))
        self.assertFalse(pace_status(1000, 700)["on_pace"])
        self.assertIn("Speed up", pace_status(1000, 700)["text"])

    def test_tryhard_bonus(self):
        self.assertEqual(tryhard_bonus(1000, 540)[0], 20)
        self.assertEqual(tryhard_bonus(1000, 600)[0], 20)          # exactly on pace counts
        self.assertEqual(tryhard_bonus(1000, 601)[0], 0)
        self.assertEqual(tryhard_bonus(250, 120)[0], TRYHARD_MIN)
        self.assertEqual(tryhard_bonus(5000, 2400)[0], TRYHARD_MAX)
        coins, text = tryhard_bonus(150, 30)
        self.assertEqual(coins, 0)
        self.assertIn("200 m", text)

    def test_calm_kinds(self):
        self.assertEqual(calm_kind("Pond bench", "by the water"), "water")
        self.assertEqual(calm_kind("Old tree", ""), "green")
        self.assertEqual(calm_kind("Library steps"), "quiet")
        self.assertEqual(calm_kind("成功湖"), "water")
        self.assertIsNone(calm_kind("Cafe corner", "busy road"))
        self.assertIsNone(calm_kind("Parking lot"))  # "park" inside another word does not count

    def test_prompts_change_daily(self):
        today = date(2026, 11, 24)
        first = calm_prompt("water", 1, today)
        self.assertIn(first, PROMPTS["water"])
        self.assertEqual(calm_prompt("water", 1, today), first)
        self.assertNotEqual(calm_prompt("water", 1, date(2026, 11, 25)), first)
        self.assertEqual(calm_spot(1, "Pond", "", today)["where"], "by the water")
        self.assertIsNone(calm_spot(1, "Cafe", "", today))

    def test_calm_bonus(self):
        self.assertEqual(calm_bonus(True, 400)[0], CALM_COINS)
        self.assertEqual(calm_bonus(True, 200)[0], 0)
        self.assertEqual(calm_bonus(False, 900)[0], 0)


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

    def coins(self, reason):
        return sum(db.session.execute(db.select(CoinTransaction.amount).where(
            CoinTransaction.user_id == self.ann.id, CoinTransaction.reason == reason)).scalars())

    def hunt(self, name, distance_m, duration_s):
        t = Treasure(name=name, lat=LAT, lon=LON)
        db.session.add(t)
        db.session.commit()
        return self.client.post("/api/journeys", json={
            "treasure_id": t.id, "distance_m": distance_m, "duration_s": duration_s, "lat": LAT, "lon": LON})

    def test_must_log_in(self):
        other = self.app.test_client()
        self.assertEqual(other.get("/api/mode").status_code, 401)
        self.assertEqual(other.post("/api/mode", json={"mode": "calm"}).status_code, 401)

    def test_pick_mode(self):
        self.assertEqual(self.client.get("/api/mode").get_json()["mode"], "normal")
        self.assertEqual(self.client.post("/api/mode", json={"mode": "zen"}).status_code, 400)
        self.assertEqual(self.client.post("/api/mode", json={"mode": "calm"}).get_json()["mode"], "calm")
        self.assertEqual(self.client.post("/api/mode", json={"mode": "tryhard"}).get_json()["mode"], "tryhard")
        self.assertEqual(self.client.get("/api/mode").get_json()["mode"], "tryhard")

    def test_pace_endpoint(self):
        self.assertTrue(self.client.get("/api/mode/pace?distance_m=1000&duration_s=500").get_json()["on_pace"])
        self.assertEqual(self.client.get("/api/mode/pace?distance_m=1000&duration_s=0").status_code, 400)

    def test_calm_spots(self):
        for name in ("Pond bench", "Cafe corner", "Library steps"):
            db.session.add(Treasure(name=name, lat=LAT, lon=LON))
        db.session.commit()
        spots = self.client.get("/api/calm-spots").get_json()["spots"]
        self.assertEqual([(s["name"], s["kind"]) for s in spots], [("Pond bench", "water"), ("Library steps", "quiet")])
        self.assertTrue(all(s["prompt"] for s in spots))

    def test_normal_mode_pays_no_bonus(self):
        self.assertIsNone(self.hunt("Pond", 1000, 500).get_json()["mode_bonus"])

    def test_tryhard_fast_hunt(self):
        self.client.post("/api/mode", json={"mode": "tryhard"})
        bonus = self.hunt("Gym", 1000, 500).get_json()["mode_bonus"]
        self.assertEqual((bonus["mode"], bonus["coins"]), ("tryhard", 20))
        self.assertEqual(self.coins("tryhard_bonus"), 20)

    def test_tryhard_slow_hunt(self):
        self.client.post("/api/mode", json={"mode": "tryhard"})
        bonus = self.hunt("Gym", 1000, 900).get_json()["mode_bonus"]
        self.assertEqual(bonus["coins"], 0)
        self.assertIn("10:00", bonus["text"])
        self.assertEqual(db.session.execute(db.select(db.func.count()).select_from(ModeBonus)).scalar(), 1)

    def test_calm_walk(self):
        self.client.post("/api/mode", json={"mode": "calm"})
        self.assertEqual(self.hunt("Pond bench", 500, 600).get_json()["mode_bonus"]["coins"], CALM_COINS)
        self.assertEqual(self.hunt("Cafe corner", 500, 600).get_json()["mode_bonus"]["coins"], 0)
        self.assertEqual(self.coins("calm_bonus"), CALM_COINS)

    def test_the_map_has_the_modes(self):
        html = self.client.get("/").get_data(as_text=True)
        for part in ('id="modePicker"', 'data-mode="tryhard"', 'data-mode="calm"', 'id="boardCalm"',
                     'id="jModeLine"', "/api/calm-spots", "/api/mode/pace"):
            self.assertIn(part, html)


if __name__ == "__main__":
    unittest.main()

"""Calories and steps from the best data we have: band heart rate, speed, or distance (energy.py)."""

import unittest
from datetime import datetime, timedelta, timezone

from app import create_app
from energy import DISTANCE, HEART, SPEED, acsm_kcal, band_covers, walk_energy
from health import calories_from_hr
from health_api import HealthDevice, HealthReading
from models import User, db


class TestFormulas(unittest.TestCase):
    def test_acsm_walking(self):
        # 750 m in 10 min = 75 m/min -> VO2 11 ml/kg/min -> 11 * 65 / 1000 * 5 * 10 min
        self.assertAlmostEqual(acsm_kcal(750, 600, 65), 35.75)

    def test_faster_burns_more_for_the_same_distance(self):
        stroll, brisk = acsm_kcal(1000, 20 * 60, 65), acsm_kcal(1000, 10 * 60, 65)
        self.assertGreater(brisk / 10, stroll / 20)  # more per minute
        self.assertGreater(acsm_kcal(1000, 5 * 60, 65), brisk)  # 12 km/h: the running equation

    def test_no_time_no_speed(self):
        self.assertIsNone(acsm_kcal(1000, 0, 65))

    def test_band_coverage(self):
        readings = [{"hr": 100}] * 60  # 60 readings * 5 s = 5 minutes
        self.assertTrue(band_covers(readings, 600))      # half of 10 minutes
        self.assertFalse(band_covers(readings, 1200))    # only a quarter of 20 minutes
        self.assertFalse(band_covers([{"hr": None}] * 200, 600))
        self.assertFalse(band_covers(readings, None))


class TestChoosingAFormula(unittest.TestCase):
    def test_distance_only(self):
        e = walk_energy(750, 65, 20)
        self.assertEqual((e["source"], e["steps"], e["calories"]), (DISTANCE, 1000, 24.4))

    def test_speed(self):
        e = walk_energy(750, 65, 20, duration_s=600)
        self.assertEqual((e["source"], e["calories"]), (SPEED, 35.8))

    def test_heart_rate_wins_when_the_band_was_on(self):
        band = [{"hr": 120, "steps": 9}] * 120  # 10 minutes of readings, 9 steps each
        e = walk_energy(750, 65, 20, duration_s=600, band=band)
        self.assertEqual(e["source"], HEART)
        self.assertEqual(e["calories"], calories_from_hr(120, 10, 65, 20))
        self.assertEqual(e["steps"], 1080)  # the band's own step count
        self.assertIn("band", e["source_text"])

    def test_band_without_steps_uses_the_distance(self):
        e = walk_energy(750, 65, 20, duration_s=600, band=[{"hr": 120, "steps": 0}] * 120)
        self.assertEqual((e["source"], e["steps"]), (HEART, 1000))

    def test_own_step_length(self):
        self.assertEqual(walk_energy(700, 65, 20, step_length_m=0.7)["steps"], 1000)


class TestApi(unittest.TestCase):
    def setUp(self):
        self.app = create_app("sqlite:///:memory:")
        self.context = self.app.app_context()
        self.context.push()
        self.player = self.app.test_client()
        self.player.post("/api/register", json={"username": "ann", "password": "secret1"})
        self.ann = db.session.execute(db.select(User).filter_by(username="ann")).scalar_one()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
        self.context.pop()

    def stats(self, query):
        return self.player.get(f"/api/walk-stats?{query}").get_json()

    def wear_band(self, minutes, hr=130, steps=10):
        device = HealthDevice(user_id=self.ann.id, name="band", token_hash="x" * 64)
        db.session.add(device)
        db.session.flush()
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        for i in range(minutes * 12):  # one reading every 5 s
            db.session.add(HealthReading(user_id=self.ann.id, device_id=device.id,
                                         at=now - timedelta(seconds=5 * i), hr=hr, steps=steps))
        db.session.commit()

    def test_a_planned_route_uses_the_distance(self):
        data = self.stats("distance_m=750")
        self.assertEqual((data["source"], data["calories"]), (DISTANCE, 24.4))

    def test_a_journey_uses_the_speed(self):
        data = self.stats("distance_m=750&duration_s=600")
        self.assertEqual((data["source"], data["calories"]), (SPEED, 35.8))

    def test_a_journey_with_the_band_uses_the_heart_rate(self):
        self.wear_band(10)
        data = self.stats("distance_m=750&duration_s=600")
        self.assertEqual(data["source"], HEART)
        self.assertEqual(data["steps"], 10 * 12 * 10)

    def test_bad_duration(self):
        self.assertEqual(self.player.get("/api/walk-stats?distance_m=750&duration_s=0").status_code, 400)

    def test_the_map_sends_the_time(self):
        html = self.player.get("/").get_data(as_text=True)
        self.assertIn("&duration_s=${seconds}", html)
        self.assertIn('id="jCalFrom"', html)


if __name__ == "__main__":
    unittest.main()

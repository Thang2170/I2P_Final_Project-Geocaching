"""B: heart-rate zone on the map: bonus coins, too-hard warnings and the cool-down quest."""

import unittest
from datetime import datetime, timedelta, timezone

from app import create_app
from health import max_heart_rate
from health_api import HealthDevice, HealthReading
from models import CoinTransaction, Journey, Treasure, User, ZoneBonus, db
from zone_coach import (COOLDOWN_REWARD, bonus_coins, bonus_seconds, cooldown_bpm, cooldown_progress,
                        longest_run, now_report, run_seconds, warning)

HR_MAX = max_heart_rate(20)  # 194: 60% = 116, 70% = 136, 80% = 155, 90% = 175
T0 = datetime(2026, 11, 24, 8, 0)
LAT, LON = 24.795324, 120.994796


def steady(hr, minutes, start=T0, every=5):
    """One reading every 5 s at the same heart rate."""
    return [(start + timedelta(seconds=every * i), hr) for i in range(minutes * 60 // every)]


class RulesTest(unittest.TestCase):
    def test_bonus_zone_is_60_to_80_percent(self):
        readings = [(T0, 110), (T0, 120), (T0, 150), (T0, 160)]
        self.assertEqual(bonus_seconds(readings, HR_MAX), 10)  # only 120 and 150

    def test_bonus_coins(self):
        self.assertEqual(bonus_coins(179), 0)
        self.assertEqual(bonus_coins(180), 1)
        self.assertEqual(bonus_coins(9 * 60), 3)
        self.assertEqual(bonus_coins(10 * 3600), 10)  # capped

    def test_run_stops_at_a_break(self):
        readings = steady(160, 5) + steady(100, 1, T0 + timedelta(minutes=5)) \
            + steady(160, 2, T0 + timedelta(minutes=6))
        self.assertEqual(run_seconds(readings, lambda hr: hr > 150), 120)

    def test_run_stops_at_a_gap(self):
        readings = steady(160, 5) + steady(160, 2, T0 + timedelta(minutes=10))
        self.assertEqual(run_seconds(readings, lambda hr: hr > 150), 120)

    def test_no_warning_when_steady(self):
        self.assertIsNone(warning(steady(140, 30), HR_MAX))
        self.assertIsNone(warning([], HR_MAX))

    def test_hard_too_long(self):
        self.assertIsNone(warning(steady(160, 9), HR_MAX))
        self.assertIn("Hard zone for 10 min", warning(steady(160, 10), HR_MAX))

    def test_maximum_too_long(self):
        self.assertIsNone(warning(steady(180, 1), HR_MAX))
        self.assertIn("Maximum for 2 min", warning(steady(180, 2), HR_MAX))

    def test_cooldown(self):
        self.assertEqual(cooldown_bpm(HR_MAX), 136)
        self.assertEqual(cooldown_progress(steady(100, 2), HR_MAX), 120)
        self.assertEqual(cooldown_progress(steady(100, 5), HR_MAX), 180)  # capped at the goal
        self.assertEqual(cooldown_progress(steady(150, 5), HR_MAX), 0)

    def test_finished_cooldown_is_kept(self):
        # 3 gentle minutes, then a climb: the cool-down still counts
        readings = steady(100, 3) + steady(150, 2, T0 + timedelta(minutes=3))
        self.assertEqual(cooldown_progress(readings, HR_MAX), 180)
        self.assertEqual(longest_run(readings, lambda hr: hr >= 150), 120)

    def test_report(self):
        self.assertFalse(now_report([], HR_MAX)["has_band"])
        report = now_report(steady(130, 6), HR_MAX)
        self.assertEqual((report["zone_name"], report["percent"], report["bonus_coins"]), ("Light", 67, 2))
        self.assertTrue(report["in_bonus_zone"])
        self.assertEqual(sum(report["zone_seconds"]), 360)


class ApiTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app("sqlite:///:memory:")
        self.context = self.app.app_context()
        self.context.push()
        self.client = self.app.test_client()
        self.client.post("/api/register", json={"username": "ann", "password": "secret1"})
        self.ann = db.session.execute(db.select(User).filter_by(username="ann")).scalar_one()
        self.device = HealthDevice(user_id=self.ann.id, name="band", token_hash="z" * 64)
        db.session.add(self.device)
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
        self.context.pop()

    def wear(self, hr, minutes, ago_s=0):
        """Readings every 5 s for `minutes`, the newest `ago_s` seconds ago (negative = from now on)."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        for i in range(minutes * 12):
            db.session.add(HealthReading(user_id=self.ann.id, device_id=self.device.id,
                                         at=now - timedelta(seconds=ago_s + 5 * i), hr=hr))
        db.session.commit()

    def coins(self):
        return sum(db.session.execute(db.select(CoinTransaction.amount)
                                      .where(CoinTransaction.user_id == self.ann.id)).scalars())

    def save_hunt(self):
        treasure = Treasure(name="Pond", lat=LAT, lon=LON)
        db.session.add(treasure)
        db.session.commit()
        return self.client.post("/api/journeys", json={
            "treasure_id": treasure.id, "distance_m": 750, "duration_s": 600, "lat": LAT, "lon": LON})

    def test_must_log_in(self):
        other = self.app.test_client()
        self.assertEqual(other.get("/api/zone/now?duration_s=60").status_code, 401)
        self.assertEqual(other.post("/api/zone/cooldown").status_code, 401)

    def test_bad_duration(self):
        self.assertEqual(self.client.get("/api/zone/now?duration_s=0").status_code, 400)

    def test_no_band(self):
        data = self.client.get("/api/zone/now?duration_s=600").get_json()
        self.assertFalse(data["has_band"])

    def test_zone_now(self):
        self.wear(130, 6)
        data = self.client.get("/api/zone/now?duration_s=600").get_json()
        self.assertEqual((data["zone_name"], data["bonus_coins"], data["max_hr"]), ("Light", 2, 194))
        self.assertIsNone(data["warning"])

    def test_warning_on_the_map(self):
        self.wear(165, 11)
        data = self.client.get("/api/zone/now?duration_s=900").get_json()
        self.assertIn("Hard zone", data["warning"])

    def test_hunt_pays_the_zone_bonus_once(self):
        self.wear(130, 10)  # 10 min in the 60-80% zone -> 3 coins
        res = self.save_hunt()
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.get_json()["zone_bonus"], 3)
        self.assertEqual(self.coins(), 3)
        self.assertEqual(db.session.execute(db.select(db.func.count()).select_from(ZoneBonus)).scalar(), 1)

    def test_hunt_without_band_pays_no_bonus(self):
        self.assertEqual(self.save_hunt().get_json()["zone_bonus"], 0)
        self.assertEqual(self.coins(), 0)

    def test_cooldown_needs_a_hunt(self):
        self.assertEqual(self.client.post("/api/zone/cooldown").status_code, 404)

    def test_cooldown_quest(self):
        self.save_hunt()
        data = self.client.post("/api/zone/cooldown").get_json()
        self.assertEqual((data["state"], data["below_bpm"]), ("no_band", 136))
        # move the hunt 4 minutes back, then walk gently since then
        journey = db.session.execute(db.select(Journey)).scalar_one()
        journey.created_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=4)
        db.session.commit()
        self.wear(100, 1)
        data = self.client.post("/api/zone/cooldown").get_json()
        self.assertEqual((data["state"], data["done_s"]), ("going", 60))
        self.wear(100, 2, ago_s=60)
        data = self.client.post("/api/zone/cooldown").get_json()
        self.assertEqual((data["state"], data["paid"]), ("done", COOLDOWN_REWARD))
        # asking again does not pay again
        self.assertEqual(self.client.post("/api/zone/cooldown").get_json()["paid"], 0)
        self.assertEqual(self.coins(), COOLDOWN_REWARD)

    def test_cooldown_missed(self):
        self.save_hunt()
        journey = db.session.execute(db.select(Journey)).scalar_one()
        journey.created_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=30)
        db.session.commit()
        self.assertEqual(self.client.post("/api/zone/cooldown").get_json()["state"], "missed")

    def test_the_map_shows_the_zone(self):
        html = self.client.get("/").get_data(as_text=True)
        for part in ('id="jZone"', 'id="jZoneWarn"', 'id="jCool"', "/api/zone/now", "/api/zone/cooldown"):
            self.assertIn(part, html)


if __name__ == "__main__":
    unittest.main()

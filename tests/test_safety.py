"""B: safety alerts (C's #7): low SpO2 or an abnormal heart rate stops the hunt with a clear warning."""

import unittest
from datetime import datetime, timedelta, timezone

from app import create_app
from health_api import HealthDevice, HealthReading
from models import SafetyAlert, User, db
from safety import check

HR_MAX = 194  # age 20
T0 = datetime(2026, 11, 24, 8, 0)


def readings(hr=None, spo2=None, seconds=60, start=T0):
    return [(start + timedelta(seconds=5 * i), hr, spo2) for i in range(seconds // 5)]


class RulesTest(unittest.TestCase):
    def test_all_fine(self):
        result = check(readings(hr=120, spo2=98), HR_MAX)
        self.assertEqual((result["level"], result["hr"], result["spo2"]), ("ok", 120, 98))
        self.assertEqual(check([], HR_MAX)["level"], "ok")

    def test_low_spo2_needs_three_in_a_row(self):
        ok = readings(hr=110, spo2=97, seconds=50)
        self.assertEqual(check(ok + readings(hr=110, spo2=88, seconds=10, start=T0 + timedelta(seconds=50)),
                               HR_MAX)["level"], "caution")  # only two low readings: maybe the band slipped
        result = check(ok + readings(hr=110, spo2=88, seconds=15, start=T0 + timedelta(seconds=50)), HR_MAX)
        self.assertEqual((result["level"], result["reason"]), ("stop", "low_spo2"))
        self.assertIn("88%", result["title"])
        self.assertIn("119", " ".join(result["advice"]))
        self.assertIn("not a medical device", result["text"])

    def test_a_gap_breaks_the_run(self):
        low = readings(spo2=89, seconds=10) + readings(spo2=89, seconds=5, start=T0 + timedelta(seconds=60))
        self.assertNotEqual(check(low, HR_MAX)["level"], "stop")

    def test_low_spo2_recovered(self):
        self.assertEqual(check(readings(spo2=88, seconds=30) + readings(spo2=97, seconds=5, start=T0 + timedelta(seconds=30)),
                               HR_MAX)["level"], "ok")

    def test_high_heart_rate(self):
        self.assertEqual(check(readings(hr=205, seconds=25), HR_MAX)["level"], "caution")
        result = check(readings(hr=205, seconds=30), HR_MAX)
        self.assertEqual((result["level"], result["reason"]), ("stop", "high_hr"))
        self.assertEqual(check(readings(hr=197, seconds=120), HR_MAX)["level"], "caution")  # within the margin

    def test_low_heart_rate(self):
        self.assertEqual(check(readings(hr=35, seconds=25), HR_MAX)["level"], "ok")
        self.assertEqual(check(readings(hr=35, seconds=30), HR_MAX)["reason"], "low_hr")

    def test_missing_values_are_skipped(self):
        mixed = [(T0 + timedelta(seconds=5 * i), None if i % 2 else 205, None) for i in range(20)]
        self.assertEqual(check(mixed, HR_MAX)["reason"], "high_hr")


class ApiTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app("sqlite:///:memory:")
        self.context = self.app.app_context()
        self.context.push()
        self.client = self.app.test_client()
        self.client.post("/api/register", json={"username": "ann", "password": "secret1"})
        self.ann = db.session.execute(db.select(User).filter_by(username="ann")).scalar_one()
        self.device = HealthDevice(user_id=self.ann.id, name="band", token_hash="s" * 64)
        db.session.add(self.device)
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
        self.context.pop()

    def wear(self, seconds, hr=110, spo2=98, ago_s=0):
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        for i in range(seconds // 5):
            db.session.add(HealthReading(user_id=self.ann.id, device_id=self.device.id,
                                         at=now - timedelta(seconds=ago_s + 5 * i), hr=hr, spo2=spo2))
        db.session.commit()

    def alerts(self):
        return db.session.execute(db.select(db.func.count()).select_from(SafetyAlert)).scalar()

    def test_must_log_in(self):
        self.assertEqual(self.app.test_client().get("/api/safety/now").status_code, 401)

    def test_no_band(self):
        data = self.client.get("/api/safety/now").get_json()
        self.assertEqual((data["level"], data["has_band"]), ("ok", False))

    def test_stop_is_saved_once(self):
        self.wear(30, spo2=87)
        for _ in range(3):
            data = self.client.get("/api/safety/now").get_json()
        self.assertEqual((data["level"], data["reason"]), ("stop", "low_spo2"))
        self.assertEqual(self.alerts(), 1)
        alerts = self.client.get("/api/safety/alerts").get_json()["alerts"]
        self.assertEqual(alerts[0]["reason"], "low_spo2")

    def test_old_readings_do_not_count(self):
        self.wear(60, spo2=85, ago_s=600)  # 10 minutes ago
        self.wear(20, spo2=97)
        self.assertEqual(self.client.get("/api/safety/now").get_json()["level"], "ok")
        self.assertEqual(self.alerts(), 0)

    def test_the_map_has_the_safety_stop(self):
        html = self.client.get("/").get_data(as_text=True)
        for part in ('id="safetyAlert"', 'role="alertdialog"', 'href="tel:119"', "/api/journey/live", "showSafety(data.safety)", "safetyStop(s)"):
            self.assertIn(part, html)


if __name__ == "__main__":
    unittest.main()

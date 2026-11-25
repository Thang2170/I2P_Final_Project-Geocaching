"""B: one live update while you walk (/api/journey/live) answers what four addresses used to."""

import unittest
from datetime import datetime, timedelta, timezone

from app import create_app
from health_api import HealthDevice, HealthReading
from models import SafetyAlert, User, WalkMode, db


class LiveTest(unittest.TestCase):
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

    def live(self, distance_m=1000, duration_s=540, client=None):
        return (client or self.client).get(f"/api/journey/live?distance_m={distance_m}&duration_s={duration_s}")

    def wear(self, seconds, hr, spo2=98):
        device = HealthDevice(user_id=self.ann.id, name="band", token_hash=f"{hr}{spo2}".ljust(64, "x"))
        db.session.add(device)
        db.session.flush()
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        for i in range(seconds // 5):
            db.session.add(HealthReading(user_id=self.ann.id, device_id=device.id, at=now - timedelta(seconds=5 * i),
                                         hr=hr, spo2=spo2, steps=10))
        db.session.commit()

    def test_bad_input(self):
        self.assertEqual(self.live(distance_m="x").status_code, 400)
        self.assertEqual(self.live(duration_s=0).status_code, 400)

    def test_same_numbers_as_the_old_addresses(self):
        self.wear(300, hr=130)
        live = self.live().get_json()
        stats = self.client.get("/api/walk-stats?distance_m=1000&duration_s=540").get_json()
        self.assertEqual((live["stats"]["steps"], live["stats"]["calories"], live["stats"]["source"]),
                         (stats["steps"], stats["calories"], stats["source"]))
        self.assertEqual(live["zone"], self.client.get("/api/zone/now?duration_s=540").get_json())
        self.assertEqual(live["safety"]["level"], self.client.get("/api/safety/now").get_json()["level"])

    def test_mode_line(self):
        self.assertEqual(self.live().get_json()["mode"], {"mode": "normal", "text": "", "on_pace": None})
        self.client.post("/api/mode", json={"mode": "tryhard"})
        fast = self.live(1000, 540).get_json()["mode"]
        self.assertEqual((fast["mode"], fast["on_pace"]), ("tryhard", True))
        self.assertIn("On pace", fast["text"])
        self.assertFalse(self.live(1000, 700).get_json()["mode"]["on_pace"])
        self.client.post("/api/mode", json={"mode": "calm"})
        self.assertIn("No rush", self.live().get_json()["mode"]["text"])

    def test_safety_stop_comes_through_and_is_saved(self):
        self.wear(30, hr=110, spo2=86)
        data = self.live().get_json()
        self.assertEqual((data["safety"]["level"], data["safety"]["reason"]), ("stop", "low_spo2"))
        self.assertEqual(db.session.execute(db.select(db.func.count()).select_from(SafetyAlert)).scalar(), 1)

    def test_warning_counts_the_minutes_before_you_pressed_start(self):
        self.wear(11 * 60, hr=165)  # 11 minutes in the Hard zone, then a journey starts
        data = self.live(duration_s=30).get_json()
        self.assertIn("Hard zone for 11 min", data["zone"]["warning"])
        self.assertEqual(data["zone"]["bonus_seconds"], 0)  # but the bonus counts this journey only

    def test_band_on_only_before_the_journey(self):
        self.wear(60, hr=130)
        with self.app.app_context():
            for r in db.session.execute(db.select(HealthReading)).scalars():
                r.at -= timedelta(minutes=2)  # the last reading is 2 minutes old
            db.session.commit()
        zone = self.live(duration_s=30).get_json()["zone"]
        self.assertEqual((zone["has_band"], zone["bonus_seconds"], sum(zone["zone_seconds"])), (True, 0, 0))

    def test_logged_out_gets_only_the_stats(self):
        data = self.live(client=self.app.test_client()).get_json()
        self.assertGreater(data["stats"]["steps"], 0)
        self.assertEqual((data["zone"], data["safety"], data["mode"]), (None, None, None))

    def test_the_map_asks_once(self):
        html = self.client.get("/").get_data(as_text=True)
        self.assertEqual(html.count("fetch(`/api/journey/live"), 1)  # one request (the other mention is a comment)
        for old in ("/api/zone/now", "/api/safety/now", "/api/mode/pace", "function checkSafety", "function loadZone"):
            self.assertNotIn(old, html)
        self.assertIn("LIVE_STILL_MS = 10000", html)  # the safety check never waits longer than 10 s


if __name__ == "__main__":
    unittest.main()

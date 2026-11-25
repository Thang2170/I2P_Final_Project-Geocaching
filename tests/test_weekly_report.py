"""B: the weekly health report (weekly_report.py, report_api.py)."""

import unittest
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

from app import create_app
from health_api import HealthDevice, HealthReading
from models import Journey, Post, SafetyAlert, TrailWalk, Treasure, User, db
from weekly_report import build_report, change_text, share_text

MON = date(2026, 11, 23)
WED = MON + timedelta(days=2)


class RulesTest(unittest.TestCase):
    def test_change_text(self):
        self.assertEqual(change_text(1100, 1000, "steps"), "+10% vs last week")
        self.assertEqual(change_text(900, 1000, "steps"), "-10% vs last week")
        self.assertEqual(change_text(1000, 1000, "steps"), "same as last week")
        self.assertEqual(change_text(500, 0, "steps"), "new this week")
        self.assertEqual(change_text(0, 0, "steps"), "")
        self.assertEqual(change_text(1100, 1000, "steps", partial=True), "+10% vs the same days last week")

    def report(self, **kw):
        days = {MON: {"steps": 2500, "active_min": 20}, WED: {"steps": 4000, "active_min": 35},
                MON - timedelta(days=7): {"steps": 5000, "active_min": 30},
                MON - timedelta(days=2): {"steps": 9000, "active_min": 60}}  # last Saturday: not compared on a Wednesday
        args = dict(monday=MON, today=WED, days=days, ring=("steps", 2000),
                    zone_seconds=[600, 1200, 900, 300, 0], hunts=[(800, 600, 40)], trails=[(1200, 900, 55)],
                    safety_stops=0, streak=3) | kw
        return build_report(**args)

    def test_bars_and_totals(self):
        r = self.report()
        self.assertEqual([b["day"] for b in r["bars"]], ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"])
        self.assertEqual([b["future"] for b in r["bars"]], [False] * 3 + [True] * 4)
        self.assertTrue(r["bars"][2]["today"])
        t = r["totals"]
        self.assertEqual((t["steps"], t["steps_change"], t["ring_days"]), (6500, "+30% vs the same days last week", 2))
        self.assertEqual((t["hunts"], t["trails"], t["distance_m"], t["calories"]), (1, 1, 2000, 95))
        self.assertTrue(r["is_current"])
        self.assertEqual(r["zones"][1], {"zone": 1, "name": "Light", "minutes": 20})

    def test_highlights(self):
        h = " ".join(self.report()["highlights"])
        self.assertIn("Best day: Wed with 4,000 steps", h)
        self.assertIn("closed your 2,000-step ring on 2 days", h)
        self.assertIn("35 min in the 60–80% heart-rate zone", h)
        quiet = self.report(days={}, zone_seconds=[], hunts=[], trails=[])
        self.assertEqual(quiet["highlights"], ["A quiet week. Plan a trail on the map to get going!"])
        self.assertEqual(quiet["zones"], [])
        self.assertIn("1 safety stop this week", " ".join(self.report(safety_stops=1)["highlights"]))

    def test_rehab_ring_is_not_drawn_on_the_steps_chart(self):
        self.assertIsNone(self.report(ring=("walk_min", 10))["ring"])

    def test_share_text_has_no_heart_data(self):
        text = share_text(self.report())
        self.assertEqual(text, "📊 My StepQuest week: 6,500 steps (+30% vs the same days last week), 2 walks "
                               "(2.0 km), and a 3-day streak 🔥.")
        self.assertNotIn("zone", text.lower())

    def test_a_finished_week_compares_all_seven_days(self):
        r = self.report(today=MON + timedelta(days=9))
        self.assertFalse(r["is_current"])
        self.assertEqual(r["totals"]["steps_change"], "-54% vs last week")  # 6,500 vs 14,000


class ApiTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app("sqlite:///:memory:")
        self.context = self.app.app_context()
        self.context.push()
        self.client = self.app.test_client()
        self.client.post("/api/register", json={"username": "ann", "password": "secret1"})
        self.ann = db.session.execute(db.select(User).filter_by(username="ann")).scalar_one()
        self.today = (datetime.now(timezone.utc) + timedelta(hours=8)).date()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
        self.context.pop()

    def taiwan_noon(self, day):
        return datetime(day.year, day.month, day.day, 4)  # 12:00 Taiwan = 04:00 UTC

    def add_week(self):
        device = HealthDevice(user_id=self.ann.id, name="band", token_hash="r" * 64)
        db.session.add(device)
        db.session.flush()
        noon = self.taiwan_noon(self.today)
        for i in range(120):  # 10 minutes at 130 bpm, 20 steps per reading
            db.session.add(HealthReading(user_id=self.ann.id, device_id=device.id, at=noon - timedelta(seconds=5 * i),
                                         hr=130, steps=20))
        t = Treasure(name="Pond", lat=24.79, lon=120.99)
        db.session.add(t)
        db.session.flush()
        db.session.add(Journey(user_id=self.ann.id, treasure_id=t.id, distance_m=800, duration_s=600, steps=1000,
                               calories=40, created_at=noon))
        db.session.add(TrailWalk(user_id=self.ann.id, checkpoints=2, distance_m=1200, duration_s=900, steps=1500,
                                 calories=55, created_at=noon))
        db.session.add(SafetyAlert(user_id=self.ann.id, reason="low_spo2", title="Low", created_at=noon))
        db.session.commit()

    def test_must_log_in(self):
        self.assertEqual(self.app.test_client().get("/api/report").status_code, 401)
        self.assertEqual(self.app.test_client().post("/api/report/share").status_code, 401)

    def test_this_week(self):
        self.add_week()
        r = self.client.get("/api/report").get_json()
        self.assertTrue(r["is_current"])
        today_bar = next(b for b in r["bars"] if b["today"])
        self.assertEqual(today_bar["steps"], 2400)  # the band's steps count on that day
        self.assertEqual((r["totals"]["hunts"], r["totals"]["trails"], r["totals"]["calories"]), (1, 1, 95))
        self.assertEqual(r["totals"]["safety_stops"], 1)
        self.assertEqual(sum(z["minutes"] for z in r["zones"]), 10)
        self.assertIsNone(r["next"])
        self.assertIsNotNone(r["previous"])

    def test_other_weeks(self):
        last = self.client.get(f"/api/report?week={(self.today - timedelta(days=7)).isoformat()}").get_json()
        self.assertFalse(last["is_current"])
        self.assertIsNone(last["totals"]["streak"])
        self.assertIsNotNone(last["next"])
        self.assertEqual(self.client.get("/api/report?week=tomorrow").status_code, 400)
        self.assertEqual(self.client.get(f"/api/report?week={(self.today + timedelta(days=8)).isoformat()}").status_code, 400)
        self.assertEqual(self.client.get("/api/report?week=2020-01-06").status_code, 400)

    def test_share_once_a_week(self):
        self.assertIn("Nothing to share", self.client.post("/api/report/share").get_json()["error"])
        self.add_week()
        res = self.client.post("/api/report/share")
        self.assertEqual(res.status_code, 201)
        self.assertIn("My StepQuest week", db.session.get(Post, res.get_json()["post_id"]).text)
        self.assertTrue(self.client.get("/api/report").get_json()["shared"])
        self.assertEqual(self.client.post("/api/report/share").status_code, 400)

    def test_pages(self):
        html = self.client.get("/report").get_data(as_text=True)
        for part in ('id="stepsChart"', "/api/report", 'id="table"', "aria-label"):
            self.assertIn(part, html)
        self.assertNotIn("innerHTML", html)
        self.assertIn('href="/report"', self.client.get("/health").get_data(as_text=True))
        self.assertIn('href="/report"', self.client.get("/welcome").get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()

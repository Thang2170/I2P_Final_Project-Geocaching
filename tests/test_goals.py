"""B: health goals with milestones (C's #4): 10,000 steps a week, 30 active minutes a day, rehab walking."""

import unittest
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

from app import create_app
from goals import daily_numbers, milestones, parse_goal, rehab_advice, rehab_minutes, week_strip
from health_api import HealthDevice, HealthReading
from models import CoinTransaction, Journey, Treasure, User, db

HR_MAX = 194  # age 20: 60% = 116, 70% = 136
WED = date(2026, 11, 25)
MONDAY = date(2026, 11, 23)


def utc(day, hour=10):
    """A UTC time on that Taiwan day (10:00 UTC is 18:00 in Taiwan)."""
    return datetime(day.year, day.month, day.day, hour)


def band(day, minutes, hr=120, steps=10):
    return [(utc(day) + timedelta(seconds=5 * i), hr, steps) for i in range(minutes * 12)]


class DailyNumbersTest(unittest.TestCase):
    def test_band_counts_steps_and_minutes(self):
        days = daily_numbers(band(WED, 30), [], HR_MAX)
        self.assertEqual(days[WED], {"steps": 3600, "active_min": 30, "walk_min": 30, "hard_share": 0.0})

    def test_slow_heart_is_walking_but_not_active(self):
        self.assertEqual(daily_numbers(band(WED, 20, hr=100), [], HR_MAX)[WED]["active_min"], 0)
        self.assertEqual(daily_numbers(band(WED, 20, hr=100), [], HR_MAX)[WED]["walk_min"], 20)

    def test_hunts_without_band(self):
        days = daily_numbers([], [(utc(WED), 900, 1200), (utc(WED), 600, 800)], HR_MAX)
        self.assertEqual((days[WED]["steps"], days[WED]["active_min"]), (2000, 25))

    def test_a_hunt_with_the_band_counts_once(self):
        days = daily_numbers(band(WED, 15), [(utc(WED), 900, 1500)], HR_MAX)
        self.assertEqual((days[WED]["steps"], days[WED]["active_min"]), (1800, 15))

    def test_taiwan_days(self):
        # 17:00 UTC on Tuesday is 01:00 on Wednesday in Taiwan
        days = daily_numbers([], [(datetime(2026, 11, 24, 17), 600, 100)], HR_MAX)
        self.assertIn(WED, days)

    def test_hard_share(self):
        days = daily_numbers(band(WED, 10, hr=150) + band(WED, 10, hr=110), [], HR_MAX)
        self.assertEqual(days[WED]["hard_share"], 0.5)


class MilestoneTest(unittest.TestCase):
    def test_parse_goal(self):
        self.assertEqual(parse_goal("rehab"), "rehab")
        with self.assertRaises(ValueError):
            parse_goal("marathon")

    def test_steps_week(self):
        days = {MONDAY: {"steps": 4000}, WED: {"steps": 2000}, WED + timedelta(days=7): {"steps": 9999}}
        items = {m["id"]: m for m in milestones("steps", days, WED, MONDAY)}
        self.assertTrue(items["steps-5000"]["done"])
        self.assertFalse(items["steps-7500"]["done"])
        self.assertEqual(items["steps-10000"]["progress"], 6000)
        self.assertEqual(items["steps-10000"]["period_start"], MONDAY)

    def test_active_day_and_week(self):
        days = {MONDAY + timedelta(days=i): {"active_min": 30} for i in range(4)}
        days[WED] = {"active_min": 22}
        items = {m["id"]: m for m in milestones("active", days, WED, MONDAY)}
        self.assertTrue(items["active-20"]["done"])
        self.assertFalse(items["active-30"]["done"])
        self.assertEqual(items["active-30"]["period_start"], WED)
        self.assertEqual(items["active-week"]["progress"], 3)  # Mon, Tue, Thu (future data, still counted)

    def test_rehab_grows_after_good_weeks(self):
        start = MONDAY - timedelta(weeks=3)
        days = {}
        for w in range(3):
            for i in range(5 if w != 1 else 3):  # the middle week had only 3 walks
                days[start + timedelta(weeks=w, days=i)] = {"walk_min": 15}
        self.assertEqual(rehab_minutes(days, start, WED), 20)  # week 1 good (10 -> 15), week 2 not, week 3 good (-> 20)
        self.assertEqual(rehab_minutes({}, start, WED), 10)
        lots = {start + timedelta(days=i): {"walk_min": 60} for i in range(21)}
        self.assertEqual(rehab_minutes(lots, start, WED), 25)
        lots = {start - timedelta(weeks=10) + timedelta(days=i): {"walk_min": 60} for i in range(100)}
        self.assertEqual(rehab_minutes(lots, start - timedelta(weeks=10), WED), 30)  # never above 30

    def test_rehab_milestones(self):
        items = {m["id"]: m for m in milestones("rehab", {WED: {"walk_min": 12}}, WED, MONDAY)}
        self.assertEqual(items["rehab-day"]["target"], 10)
        self.assertTrue(items["rehab-day"]["done"])
        self.assertEqual(items["rehab-week"]["progress"], 1)

    def test_rehab_advice(self):
        self.assertIsNone(rehab_advice({WED: {"hard_share": 0.1}}, WED, HR_MAX))
        self.assertIn("136 bpm", rehab_advice({WED: {"hard_share": 0.4}}, WED, HR_MAX))

    def test_week_strip(self):
        strip = week_strip("active", {MONDAY: {"active_min": 31}}, WED, MONDAY)
        self.assertEqual([d["day"] for d in strip][:3], ["Mon", "Tue", "Wed"])
        self.assertTrue(strip[0]["met"])
        self.assertTrue(strip[4]["future"])


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

    def wear(self, minutes, hr=120, steps=10):
        device = HealthDevice(user_id=self.ann.id, name="band", token_hash=f"{minutes}{hr}".ljust(64, "g"))
        db.session.add(device)
        db.session.flush()
        # Noon today, Taiwan time (04:00 UTC), so all the minutes fall on "today" even when the
        # tests run just after midnight (readings ending "now" at 00:04 were mostly yesterday's).
        taiwan_today = (datetime.now(timezone.utc) + timedelta(hours=8)).date()
        noon = datetime(taiwan_today.year, taiwan_today.month, taiwan_today.day, 4)
        for i in range(minutes * 12):
            db.session.add(HealthReading(user_id=self.ann.id, device_id=device.id,
                                         at=noon - timedelta(seconds=5 * i), hr=hr, steps=steps))
        db.session.commit()

    def coins(self):
        return sum(db.session.execute(db.select(CoinTransaction.amount)
                                      .where(CoinTransaction.user_id == self.ann.id)).scalars())

    def test_must_log_in(self):
        other = self.app.test_client()
        self.assertEqual(other.get("/api/goal").status_code, 401)
        self.assertEqual(other.post("/api/goal", json={"goal": "steps"}).status_code, 401)

    def test_pick_a_goal(self):
        data = self.client.get("/api/goal").get_json()
        self.assertIsNone(data["goal"])
        self.assertEqual([c["id"] for c in data["choices"]], ["steps", "active", "rehab"])
        self.assertEqual(self.client.post("/api/goal", json={"goal": "fly"}).status_code, 400)
        data = self.client.post("/api/goal", json={"goal": "active"}).get_json()
        self.assertEqual((data["goal"], len(data["milestones"]), len(data["week"])), ("active", 4, 7))
        self.assertEqual(len(self.client.get("/api/goal/choices").get_json()["choices"]), 3)

    def test_collect_once(self):
        self.client.post("/api/goal", json={"goal": "active"})
        self.wear(12)
        self.assertEqual(self.client.post("/api/goal/milestones/active-20/claim").status_code, 400)
        res = self.client.post("/api/goal/milestones/active-10/claim")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["coins_earned"], 1)
        again = self.client.post("/api/goal/milestones/active-10/claim")
        self.assertEqual(again.status_code, 400)
        self.assertEqual(self.coins(), 1)
        claimed = {m["id"]: m["claimed"] for m in self.client.get("/api/goal").get_json()["milestones"]}
        self.assertTrue(claimed["active-10"])

    def test_milestone_must_match_your_goal(self):
        self.assertEqual(self.client.post("/api/goal/milestones/steps-2500/claim").status_code, 400)
        self.client.post("/api/goal", json={"goal": "active"})
        self.assertEqual(self.client.post("/api/goal/milestones/steps-2500/claim").status_code, 404)

    def test_steps_from_hunts(self):
        self.client.post("/api/goal", json={"goal": "steps"})
        treasure = Treasure(name="Pond", lat=24.795324, lon=120.994796)
        db.session.add(treasure)
        db.session.flush()
        db.session.add(Journey(user_id=self.ann.id, treasure_id=treasure.id, distance_m=2000,
                               duration_s=1500, steps=2700, calories=90))
        db.session.commit()
        items = {m["id"]: m for m in self.client.get("/api/goal").get_json()["milestones"]}
        self.assertTrue(items["steps-2500"]["done"])
        self.assertEqual(items["steps-10000"]["progress"], 2700)

    def test_changing_goal_restarts_rehab(self):
        self.client.post("/api/goal", json={"goal": "rehab"})
        later = datetime.now(timezone.utc) + timedelta(days=30)
        with patch("goal_api.datetime") as fake:
            fake.now.return_value = later
            fake.combine, fake.min = datetime.combine, datetime.min
            data = self.client.post("/api/goal", json={"goal": "steps"}).get_json()
        self.assertEqual(data["started_on"], (later + timedelta(hours=8)).date().isoformat())

    def test_rehab_advice_when_too_hard(self):
        self.client.post("/api/goal", json={"goal": "rehab"})
        self.wear(15, hr=160)
        data = self.client.get("/api/goal").get_json()
        self.assertIn("slow down", data["advice"])

    def test_home_page_has_the_card(self):
        html = self.client.get("/welcome").get_data(as_text=True)
        if 'id="goalCard"' not in html:
            html = self.client.get("/").get_data(as_text=True)
        for part in ('id="goalCard"', "/api/goal", "claimMilestone"):
            self.assertIn(part, html)


if __name__ == "__main__":
    unittest.main()

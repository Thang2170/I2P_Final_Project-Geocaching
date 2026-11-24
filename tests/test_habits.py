"""B: daily goal ring, streak freezes and sharing a streak (C's #8)."""

import unittest
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

from app import create_app
from habits import (FREEZE_PRICE, MAX_FREEZES, freeze_problem, freezes_to_use, ring, ring_days, ring_target,
                    share_text)
from health_api import HealthDevice, HealthReading
from models import CoinTransaction, GoalChoice, Post, StreakFreeze, User, db

WED = date(2026, 11, 25)
D = timedelta(days=1)


class RingTest(unittest.TestCase):
    def test_targets_follow_the_goal(self):
        self.assertEqual(ring_target(None, {}, WED, WED), ("steps", 2000))
        self.assertEqual(ring_target("steps", {}, WED, WED), ("steps", 1500))
        self.assertEqual(ring_target("active", {}, WED, WED), ("active_min", 30))
        self.assertEqual(ring_target("rehab", {}, WED, WED), ("walk_min", 10))

    def test_ring(self):
        r = ring(None, {WED: {"steps": 500}}, WED, WED)
        self.assertEqual((r["percent"], r["closed"]), (25, False))
        self.assertIn("1,500 steps to close", r["text"])
        r = ring("active", {WED: {"active_min": 45}}, WED, WED)
        self.assertEqual((r["percent"], r["closed"]), (100, True))

    def test_ring_days(self):
        days = {WED: {"steps": 2500}, WED - D: {"steps": 100}, WED - 100 * D: {"steps": 9000}}
        self.assertEqual(ring_days(None, days, WED, WED), {WED})  # 100 days ago is too long ago


class FreezeTest(unittest.TestCase):
    def test_one_missed_day(self):
        active = {WED - 3 * D, WED - 2 * D}
        self.assertEqual(freezes_to_use(active, set(), WED, [WED - 5 * D]), [WED - D])

    def test_no_gap_no_freeze(self):
        self.assertEqual(freezes_to_use({WED - D}, set(), WED, [WED - 5 * D]), [])

    def test_two_missed_days_need_two_freezes(self):
        active = {WED - 3 * D}
        self.assertEqual(freezes_to_use(active, set(), WED, [WED - 9 * D]), [])
        self.assertEqual(freezes_to_use(active, set(), WED, [WED - 9 * D, WED - 8 * D]), [WED - 2 * D, WED - D])

    def test_an_older_gap_inside_the_streak(self):
        active = {WED - D, WED - 2 * D, WED - 4 * D}
        self.assertEqual(freezes_to_use(active, set(), WED, [WED - 6 * D]), [WED - 3 * D])

    def test_two_gaps_two_freezes(self):
        active = {WED - 2 * D, WED - 4 * D}
        self.assertEqual(freezes_to_use(active, set(), WED, [WED - 9 * D, WED - 9 * D]), [WED - 3 * D, WED - D])
        # with one freeze only the newest gap is covered, and the streak stops at the older one
        self.assertEqual(freezes_to_use(active, set(), WED, [WED - 9 * D]), [WED - D])

    def test_too_long_a_gap(self):
        self.assertEqual(freezes_to_use({WED - 5 * D}, set(), WED, [WED - 9 * D] * 2), [])

    def test_freeze_must_be_bought_before_the_missed_day(self):
        active = {WED - 2 * D}
        self.assertEqual(freezes_to_use(active, set(), WED, [WED]), [])        # bought today: too late
        self.assertEqual(freezes_to_use(active, set(), WED, [WED - D]), [])    # bought on the day itself
        self.assertEqual(freezes_to_use(active, set(), WED, [WED - 2 * D]), [WED - D])

    def test_already_frozen_days_count(self):
        self.assertEqual(freezes_to_use({WED - 3 * D}, {WED - 2 * D}, WED, [WED - 5 * D]), [WED - D])

    def test_nothing_to_protect(self):
        self.assertEqual(freezes_to_use(set(), set(), WED, [WED - 5 * D]), [])

    def test_buying(self):
        self.assertIsNone(freeze_problem(0, FREEZE_PRICE))
        self.assertIn("at most", freeze_problem(MAX_FREEZES, 999))
        self.assertIn("costs", freeze_problem(0, FREEZE_PRICE - 1))


class ShareTextTest(unittest.TestCase):
    def test_text(self):
        self.assertIn("5-day streak", share_text(5, 9, False))
        self.assertIn("best is 9", share_text(5, 9, False))
        self.assertIn("best ever", share_text(5, 5, True))
        self.assertIn("ring is closed", share_text(5, 5, True))
        with self.assertRaises(ValueError):
            share_text(0, 3, False)


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

    def give(self, coins):
        db.session.add(CoinTransaction(user_id=self.ann.id, amount=coins, reason="gift"))
        db.session.commit()

    def walk_steps(self, days_ago, steps=2100):
        """Band steps on a Taiwan day: 04:00 UTC is noon in Taiwan."""
        device = db.session.execute(db.select(HealthDevice)).scalar() or HealthDevice(
            user_id=self.ann.id, name="band", token_hash="h" * 64)
        db.session.add(device)
        db.session.flush()
        day = (datetime.now(timezone.utc) + timedelta(hours=8)).date() - timedelta(days=days_ago)  # Taiwan date
        noon = datetime(day.year, day.month, day.day, 4)
        for i in range(steps // 100):
            db.session.add(HealthReading(user_id=self.ann.id, device_id=device.id,
                                         at=noon + timedelta(seconds=5 * i), hr=100, steps=100))
        db.session.commit()

    def test_must_log_in(self):
        other = self.app.test_client()
        self.assertEqual(other.get("/api/habits").status_code, 401)
        self.assertEqual(other.post("/api/habits/freeze").status_code, 401)
        self.assertEqual(other.post("/api/habits/share").status_code, 401)

    def test_ring_counts_for_the_streak(self):
        data = self.client.get("/api/habits").get_json()
        self.assertEqual((data["current"], data["ring"]["target"]), (0, 2000))
        self.walk_steps(1)
        self.walk_steps(2)
        data = self.client.get("/api/habits").get_json()
        self.assertEqual(data["current"], 2)
        # the "This week" card shows the same streak
        self.assertEqual(self.client.get("/api/challenges").get_json()["streak"]["current"], 2)

    def test_ring_follows_the_goal(self):
        db.session.add(GoalChoice(user_id=self.ann.id, goal="active", started_on=date(2026, 11, 1)))
        db.session.commit()
        self.assertEqual(self.client.get("/api/habits").get_json()["ring"]["unit"], "active min")

    def test_buy_freeze(self):
        self.assertEqual(self.client.post("/api/habits/freeze").status_code, 400)  # no coins
        self.give(100)
        data = self.client.post("/api/habits/freeze").get_json()
        self.assertEqual((data["freezes"]["owned"], data["balance"]), (1, 100 - FREEZE_PRICE))
        self.client.post("/api/habits/freeze")
        self.assertIn("at most", self.client.post("/api/habits/freeze").get_json()["error"])

    def test_a_freeze_saves_the_streak(self):
        self.walk_steps(2)
        self.walk_steps(3)
        today = datetime.now(timezone.utc) + timedelta(hours=8)
        db.session.add(StreakFreeze(user_id=self.ann.id, bought_on=today.date() - timedelta(days=5)))
        db.session.commit()
        data = self.client.get("/api/habits").get_json()
        self.assertEqual(len(data["used_freeze_now"]), 1)
        self.assertEqual((data["current"], data["freezes"]["owned"]), (3, 0))
        # asking again does not use another one
        self.assertEqual(self.client.get("/api/habits").get_json()["used_freeze_now"], [])

    def test_share_streak(self):
        self.assertEqual(self.client.post("/api/habits/share").status_code, 400)  # no streak yet
        self.walk_steps(0)
        res = self.client.post("/api/habits/share")
        self.assertEqual(res.status_code, 201)
        post = db.session.get(Post, res.get_json()["post_id"])
        self.assertIn("1-day streak", post.text)
        self.assertTrue(self.client.get("/api/habits").get_json()["shared_today"])
        self.assertEqual(self.client.post("/api/habits/share").status_code, 400)  # once a day
        feed = self.client.get("/api/feed").get_data(as_text=True)
        self.assertIn("1-day streak", feed)

    def test_home_page_has_the_ring(self):
        html = self.client.get("/welcome").get_data(as_text=True)
        for part in ('id="ring"', 'id="buyFreeze"', 'id="shareStreak"', "/api/habits"):
            self.assertIn(part, html)


if __name__ == "__main__":
    unittest.main()

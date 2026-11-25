"""B: the evening "streak at risk" reminder in the bell (habits.py, habit_api.remind_if_at_risk)."""

import unittest
from datetime import date, datetime, timedelta
from unittest.mock import patch

from app import create_app
from habits import streak_at_risk, streak_risk_text
from models import Journey, Notification, StreakFreeze, StreakReminder, Treasure, User, db

TODAY = date(2026, 11, 25)


def taiwan(hour, minute=0, day=TODAY):
    return datetime(day.year, day.month, day.day, hour, minute)


class RulesTest(unittest.TestCase):
    def test_when(self):
        self.assertFalse(streak_at_risk(5, False, 19))   # too early
        self.assertTrue(streak_at_risk(5, False, 20))
        self.assertFalse(streak_at_risk(5, True, 22))    # already active today
        self.assertFalse(streak_at_risk(0, False, 22))   # no streak to lose

    def test_words(self):
        self.assertIn("6-day streak ends at midnight", streak_risk_text(6, 0))
        self.assertIn("1-day streak", streak_risk_text(1, 0))
        self.assertNotIn("freeze", streak_risk_text(6, 0))
        self.assertIn("1 freeze ready", streak_risk_text(6, 1))
        self.assertIn("2 freezes ready", streak_risk_text(6, 2))


class BellTest(unittest.TestCase):
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

    def hunt_on(self, day):
        """A finished hunt at 18:00 Taiwan time (10:00 UTC) on that day: an active day."""
        t = Treasure(name=f"T{day}", lat=24.79, lon=120.99)
        db.session.add(t)
        db.session.flush()
        db.session.add(Journey(user_id=self.ann.id, treasure_id=t.id, distance_m=300, duration_s=300, steps=400,
                               calories=10, created_at=datetime(day.year, day.month, day.day, 10)))
        db.session.commit()

    def bell(self, local):
        """Ask the bell as if it were `local` (Taiwan time)."""
        with patch("habit_api._local_now", return_value=local), \
                patch("habit_api._today", return_value=local.date()):
            return self.client.get("/api/notifications").get_json()

    def streak_items(self, data):
        return [i for i in data["items"] if i["kind"] == "streak_risk"]

    def test_reminds_once_in_the_evening(self):
        for days_ago in (1, 2, 3):
            self.hunt_on(TODAY - timedelta(days=days_ago))
        self.assertEqual(self.streak_items(self.bell(taiwan(19, 59))), [])      # not yet
        data = self.bell(taiwan(20, 1))
        items = self.streak_items(data)
        self.assertEqual(len(items), 1)
        self.assertIn("3-day streak ends at midnight", items[0]["text"])
        self.assertEqual((items[0]["link"], data["unseen"]), ("/welcome", 1))
        for minute in (2, 30):
            self.assertEqual(len(self.streak_items(self.bell(taiwan(20, minute)))), 1)  # never twice
        self.assertEqual(db.session.execute(db.select(db.func.count()).select_from(StreakReminder)).scalar(), 1)

    def test_no_reminder_if_you_were_active_today(self):
        self.hunt_on(TODAY - timedelta(days=1))
        self.hunt_on(TODAY)
        self.assertEqual(self.streak_items(self.bell(taiwan(21))), [])
        self.assertEqual(db.session.execute(db.select(db.func.count()).select_from(Notification)).scalar(), 0)

    def test_no_reminder_without_a_streak(self):
        self.assertEqual(self.streak_items(self.bell(taiwan(21))), [])

    def test_mentions_a_ready_freeze(self):
        self.hunt_on(TODAY - timedelta(days=1))
        db.session.add(StreakFreeze(user_id=self.ann.id, bought_on=TODAY - timedelta(days=5)))
        db.session.commit()
        text = self.streak_items(self.bell(taiwan(22)))[0]["text"]
        self.assertIn("1 freeze ready", text)

    def test_next_evening_is_a_new_check(self):
        self.hunt_on(TODAY - timedelta(days=1))
        self.bell(taiwan(20))
        self.hunt_on(TODAY)  # walked late tonight: tomorrow's streak is 2 days
        tomorrow = TODAY + timedelta(days=1)
        items = self.streak_items(self.bell(taiwan(20, 30, tomorrow)))
        self.assertEqual(len(items), 2)
        self.assertIn("2-day streak", items[0]["text"])  # newest first
        self.assertIn("1-day streak", items[1]["text"])  # the words of that evening stay


if __name__ == "__main__":
    unittest.main()

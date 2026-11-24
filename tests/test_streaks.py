"""Daily streaks and weekly challenges (streaks.py, challenge_api.py, the welcome page)."""

import unittest
from datetime import date, datetime, timedelta, timezone

from app import create_app
from models import ChallengeClaim, Journey, Treasure, User, db
from streaks import (CHALLENGE_REWARD, CHALLENGES, challenge_list, claim_problem, local_day, streaks,
                     week_numbers, week_start)

TUE = date(2026, 11, 24)  # a Tuesday


def utc(y, m, d, h=12):
    return datetime(y, m, d, h, tzinfo=timezone.utc)


class TestRules(unittest.TestCase):
    def test_taiwan_days(self):
        self.assertEqual(local_day(utc(2026, 11, 24, 17)), date(2026, 11, 25))  # 1 a.m. in Taiwan
        self.assertEqual(local_day(datetime(2026, 11, 24, 15, 59)), date(2026, 11, 24))  # no zone = UTC

    def test_week_starts_on_monday(self):
        self.assertEqual(week_start(TUE), date(2026, 11, 23))
        self.assertEqual(week_start(date(2026, 11, 29)), date(2026, 11, 23))  # Sunday

    def test_streaks(self):
        days = {TUE - timedelta(days=i) for i in range(3)}
        self.assertEqual(streaks(days, TUE), (3, 3))
        # not walked yet today: yesterday's streak is still alive
        self.assertEqual(streaks(days - {TUE}, TUE), (2, 2))
        # missed yesterday too: the streak is over, but the best is kept
        self.assertEqual(streaks({TUE - timedelta(days=5), TUE - timedelta(days=6)}, TUE), (0, 2))
        self.assertEqual(streaks(set(), TUE), (0, 0))

    def test_week_numbers(self):
        monday = date(2026, 11, 23)
        finds = [(utc(2026, 11, 23), 10), (utc(2026, 11, 24), 24), (utc(2026, 11, 10), 30)]  # last one: old week
        hunts = [(utc(2026, 11, 25), 1500.4), (utc(2026, 11, 26), 700)]
        self.assertEqual(week_numbers(finds, hunts, monday),
                         {"finds": 2, "distance": 2200, "days": 4, "bounty": 1})

    def test_list_and_claims(self):
        numbers = {"finds": 5, "distance": 100, "days": 4, "bounty": 0}
        items = {c["id"]: c for c in challenge_list(numbers, {"days"})}
        self.assertEqual(set(items), set(CHALLENGES))
        self.assertEqual((items["finds"]["progress"], items["finds"]["done"]), (3, True))  # capped at the goal
        self.assertTrue(items["days"]["claimed"])
        self.assertEqual(items["distance"]["text"], "0.1 / 2 km")  # Python writes the progress words
        self.assertIsNone(claim_problem("finds", numbers, set()))
        self.assertIn("already", claim_problem("days", numbers, {"days"}))
        self.assertIn("Not done", claim_problem("distance", numbers, set()))
        self.assertEqual(claim_problem("fly", numbers, set()), "No such challenge")


class TestApi(unittest.TestCase):
    def setUp(self):
        self.app = create_app("sqlite:///:memory:")
        self.context = self.app.app_context()
        self.context.push()
        self.player = self.app.test_client()
        self.player.post("/api/register", json={"username": "ann", "password": "secret1"})
        self.ann = db.session.execute(db.select(User).filter_by(username="ann")).scalar_one()
        self.treasures = []
        for i in range(3):
            t = Treasure(name=f"T{i}", lat=24.70 + i * 0.01, lon=120.9)
            db.session.add(t)
            self.treasures.append(t)
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
        self.context.pop()

    def week(self):
        return self.player.get("/api/challenges").get_json()

    def find(self, t):
        return self.player.post(f"/api/treasures/{t.id}/claim", json={"lat": t.lat, "lon": t.lon})

    def test_needs_login(self):
        self.assertEqual(self.app.test_client().get("/api/challenges").status_code, 401)
        self.assertEqual(self.app.test_client().post("/api/challenges/finds/claim").status_code, 401)

    def test_a_new_player(self):
        data = self.week()
        self.assertEqual(data["streak"], {"current": 0, "best": 0, "today_done": False})
        self.assertEqual(len(data["challenges"]), len(CHALLENGES))

    def test_a_find_starts_a_streak(self):
        self.find(self.treasures[0])
        self.assertEqual(self.week()["streak"], {"current": 1, "best": 1, "today_done": True})

    def test_claiming(self):
        self.assertEqual(self.player.post("/api/challenges/finds/claim").status_code, 400)  # not done
        for t in self.treasures:
            self.find(t)
        before = self.player.get("/api/coins").get_json()["balance"]
        r = self.player.post("/api/challenges/finds/claim")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["balance"], before + CHALLENGE_REWARD)
        finds = next(c for c in r.get_json()["challenges"] if c["id"] == "finds")
        self.assertTrue(finds["claimed"])
        self.assertEqual(self.player.post("/api/challenges/finds/claim").status_code, 400)  # only once a week
        self.assertEqual(db.session.query(ChallengeClaim).count(), 1)
        self.assertEqual(self.player.post("/api/challenges/fly/claim").status_code, 404)

    def test_hunts_count_for_distance(self):
        for t, m in zip(self.treasures, (1200, 900)):  # one saved hunt per treasure
            db.session.add(Journey(user_id=self.ann.id, treasure_id=t.id, distance_m=m,
                                   duration_s=600, steps=1000, calories=30))
        db.session.commit()
        distance = next(c for c in self.week()["challenges"] if c["id"] == "distance")
        self.assertTrue(distance["done"])

    def test_welcome_page(self):
        html = self.player.get("/welcome").get_data(as_text=True)
        self.assertIn('id="weekCard"', html)
        self.assertIn('getJson("/api/challenges")', html)
        self.assertNotIn(".innerHTML", html)


if __name__ == "__main__":
    unittest.main()

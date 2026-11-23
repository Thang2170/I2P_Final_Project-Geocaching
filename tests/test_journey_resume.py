import unittest
from datetime import datetime, timedelta, timezone

from app import create_app
from journey_resume import (MAX_WINDOW_S, MIN_WINDOW_S, can_resume, deadline_for, expected_walk_s,
                            parse_progress, resume_window_s, seconds_left)
from journey_resume_api import ActiveJourney
from models import db

NOW = datetime(2026, 11, 24, 2, 0, 0, tzinfo=timezone.utc)
AT_NTHU = {"lat": 24.795324, "lon": 120.994796}


class TestRules(unittest.TestCase):
    def test_short_walk_gets_the_minimum(self):
        self.assertEqual(resume_window_s(50), MIN_WINDOW_S)

    def test_window_grows_with_the_distance(self):
        # 1 km straight: about 1400 m walked at 1 m/s = 1400 s, x2 + 600 s = 3400 s (about 57 min)
        self.assertAlmostEqual(expected_walk_s(1000), 1400)
        self.assertEqual(resume_window_s(1000), 3400)
        self.assertGreater(resume_window_s(2000), resume_window_s(1000))

    def test_very_long_walk_is_capped(self):
        self.assertEqual(resume_window_s(100_000), MAX_WINDOW_S)

    def test_deadline_and_seconds_left(self):
        deadline = deadline_for(NOW, 1000)
        self.assertEqual(deadline, NOW + timedelta(seconds=3400))
        self.assertEqual(seconds_left(deadline, NOW + timedelta(seconds=400)), 3000)
        self.assertEqual(seconds_left(deadline, NOW + timedelta(hours=5)), 0)
        self.assertTrue(can_resume(deadline, NOW))
        self.assertFalse(can_resume(deadline, NOW + timedelta(seconds=3401)))

    def test_time_without_a_zone_counts_as_utc(self):
        naive = datetime(2026, 11, 24, 2, 0, 0)
        self.assertTrue(can_resume(naive + timedelta(minutes=5), NOW))

    def test_progress_parsing(self):
        self.assertEqual(parse_progress({"meters": "120.44", "elapsed_s": 95.7}), (120.4, 95))
        for bad in [None, {}, {"meters": "x", "elapsed_s": 1}, {"meters": -1, "elapsed_s": 1},
                    {"meters": 1, "elapsed_s": 10 ** 9}]:
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    parse_progress(bad)


class TestActiveJourneyApi(unittest.TestCase):
    def setUp(self):
        self.app = create_app("sqlite:///:memory:")
        self.context = self.app.app_context()
        self.context.push()
        self.bao = self.app.test_client()
        self.bao.post("/api/register", json={"username": "bao", "password": "secret1"})
        self.tid = self.bao.get("/api/treasures").get_json()[0]["id"]

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
        self.context.pop()

    def start(self, lat=24.7955, lon=120.9965):
        return self.bao.post("/api/journeys/active", json={"treasure_id": self.tid, "lat": lat, "lon": lon})

    def test_start_gives_a_window_that_fits_the_walk(self):
        r = self.start()  # about 173 m from the treasure
        data = r.get_json()
        self.assertEqual(r.status_code, 201)
        # 173 m straight: about 243 m walked at 1 m/s, x2 + 10 min = about 18 minutes
        self.assertTrue(1050 <= data["window_s"] <= 1120, data["window_s"])
        self.assertEqual(data["treasure"]["name"], "National Tsing Hua University")
        far = self.start(lat=24.8138, lon=120.9675).get_json()  # about 3.4 km away
        self.assertGreater(far["window_s"], 2 * 3600)

    def test_progress_then_carry_on_after_a_reload(self):
        self.start()
        self.bao.post("/api/journeys/active/progress", json={"meters": 80, "elapsed_s": 60})
        self.bao.post("/api/journeys/active/progress", json={"meters": 40, "elapsed_s": 30})  # a late old report
        active = self.bao.get("/api/journeys/active").get_json()["active"]
        self.assertEqual((active["meters"], active["elapsed_s"]), (80, 60))  # never goes backwards
        self.assertGreater(active["seconds_left"], 0)

    def test_after_the_deadline_it_is_reported_once_then_gone(self):
        self.start()
        row = db.session.get(ActiveJourney, 1)
        row.deadline = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.session.commit()
        first = self.bao.get("/api/journeys/active").get_json()
        self.assertIsNone(first["active"])
        self.assertEqual(first["expired"]["treasure"], "National Tsing Hua University")
        self.assertEqual(self.bao.get("/api/journeys/active").get_json(), {"active": None})
        self.assertEqual(self.bao.post("/api/journeys/active/progress",
                                       json={"meters": 1, "elapsed_s": 1}).status_code, 404)

    def test_finishing_forgets_it(self):
        self.start()
        self.assertEqual(self.bao.delete("/api/journeys/active").status_code, 200)
        self.assertEqual(self.bao.get("/api/journeys/active").get_json(), {"active": None})

    def test_starting_again_replaces_the_old_one(self):
        self.start()
        self.bao.post("/api/journeys/active/progress", json={"meters": 80, "elapsed_s": 60})
        self.start()
        self.assertEqual(len(db.session.execute(db.select(ActiveJourney)).scalars().all()), 1)
        self.assertEqual(self.bao.get("/api/journeys/active").get_json()["active"]["meters"], 0)

    def test_bad_requests(self):
        self.assertEqual(self.bao.post("/api/journeys/active", json={"lat": 1}).status_code, 400)
        self.assertEqual(self.bao.post("/api/journeys/active",
                                       json={"treasure_id": 999, **AT_NTHU}).status_code, 404)
        self.assertEqual(self.bao.post("/api/journeys/active/progress", json={"meters": "x"}).status_code, 400)
        logged_out = self.app.test_client()
        for call in (logged_out.get, logged_out.delete):
            self.assertEqual(call("/api/journeys/active").status_code, 401)


if __name__ == "__main__":
    unittest.main()

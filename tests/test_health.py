import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

import requests

from app import create_app
from health import (calories_from_hr, heart_chart_points, max_heart_rate, parse_batch, resting_estimate,
                    rules_advice, split_walks, summarize, vo2max_estimate, zone_of)
from health_ai import analyse, build_prompt
from health_api import HealthDevice, HealthReading, hash_token
from models import db

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "esp32"))
from simulate_walk import fake_walk  # noqa: E402

START = datetime(2026, 11, 24, 8, 0, tzinfo=timezone.utc)


def walk(heart_rates, every_s=5, steps=10, spo2=97.5):
    return [{"at": START + timedelta(seconds=i * every_s), "hr": hr, "spo2": spo2, "steps": steps}
            for i, hr in enumerate(heart_rates)]


class TestRules(unittest.TestCase):
    def test_max_heart_rate_and_zones(self):
        self.assertEqual(max_heart_rate(20), 194)
        self.assertEqual(zone_of(100, 194), 0)   # 52 %: very light
        self.assertEqual(zone_of(140, 194), 2)   # 72 %: moderate
        self.assertEqual(zone_of(190, 194), 4)   # 98 %: maximum

    def test_resting_and_vo2max(self):
        self.assertEqual(resting_estimate([60, 62, 90, 100, 110, 120, 130, 140, 150, 160]), 60)
        self.assertIsNone(resting_estimate([80, 90]))
        self.assertEqual(vo2max_estimate(194, 60), 49.5)
        self.assertIsNone(vo2max_estimate(194, None))

    def test_calories(self):
        self.assertGreater(calories_from_hr(120, 30, 65, 20), 100)
        self.assertIsNone(calories_from_hr(None, 30, 65, 20))
        self.assertEqual(calories_from_hr(40, 10, 65, 20), 0)  # never below zero

    def test_walks_are_split_at_long_pauses(self):
        readings = walk([80] * 3) + [{"at": START + timedelta(hours=1), "hr": 80, "spo2": None, "steps": 0}]
        self.assertEqual([len(w) for w in split_walks(readings)], [3, 1])

    def test_summary(self):
        s = summarize(walk([90 + i for i in range(60)]), age=20, weight_kg=65)  # 5 minutes
        self.assertEqual((s["steps"], s["distance_m"], s["hr_max"], s["spo2_min"]), (600, 450, 149, 97.5))
        self.assertAlmostEqual(s["minutes"], 5.0, delta=0.1)
        self.assertAlmostEqual(sum(z["minutes"] for z in s["zones"]), s["minutes"], delta=0.2)
        self.assertGreater(s["cadence_spm"], 100)

    def test_advice_mentions_low_oxygen_carefully(self):
        s = summarize(walk([100] * 20, spo2=89.0))
        text = " ".join(rules_advice(s))
        self.assertIn("89.0 %", text)
        self.assertIn("sensor", text)

    def test_chart_points(self):
        points = heart_chart_points(walk([80, 100, 120]))
        self.assertEqual(len(points.split()), 3)
        self.assertEqual(heart_chart_points(walk([80])), "")

    def test_parse_batch(self):
        clean = parse_batch({"readings": [{"age_s": 10, "hr": "88", "spo2": 97.4, "steps": 9}]})
        self.assertEqual(clean[0], {"age_s": 10, "hr": 88, "spo2": 97.4, "steps": 9, "temp_c": None})
        for bad in [None, {}, {"readings": []}, {"readings": [{"hr": 500}]}, {"readings": [{"hr": "x"}]},
                    {"readings": [{"age_s": -1}]}, {"readings": [1]}]:
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    parse_batch(bad)


class TestLocalAI(unittest.TestCase):
    def setUp(self):
        self.summary = summarize(walk([90 + i for i in range(60)]))

    def test_prompt_has_the_numbers_and_the_rules(self):
        prompt = build_prompt(self.summary)
        self.assertIn("149", prompt)
        self.assertIn("Do not diagnose", prompt)

    def test_uses_ollama_when_it_runs(self):
        answer = Mock(status_code=200)
        answer.json.return_value = {"response": "  Great walk! Keep it up.  "}
        with patch("health_ai.requests.post", return_value=answer) as post:
            result = analyse(self.summary)
        self.assertEqual(result["text"], "Great walk! Keep it up.")
        self.assertIn("local AI", result["source"])
        self.assertEqual(post.call_args.kwargs["json"]["model"], "qwen2.5:7b")

    def test_falls_back_to_rules_when_ollama_is_off(self):
        with patch("health_ai.requests.post", side_effect=requests.ConnectionError()):
            result = analyse(self.summary)
        self.assertEqual(result["source"], "StepQuest rules")
        self.assertIn("steps", result["text"])

    def test_falls_back_on_a_bad_answer(self):
        for answer in [Mock(status_code=500), Mock(status_code=200, json=Mock(return_value={"response": ""}))]:
            with self.subTest(answer=answer):
                with patch("health_ai.requests.post", return_value=answer):
                    self.assertEqual(analyse(self.summary)["source"], "StepQuest rules")


class TestHealthApi(unittest.TestCase):
    def setUp(self):
        self.app = create_app("sqlite:///:memory:")
        self.context = self.app.app_context()
        self.context.push()
        self.bao = self.app.test_client()
        self.bao.post("/api/register", json={"username": "bao", "password": "secret1"})
        self.token = self.bao.post("/api/health/devices", json={"name": "Wrist"}).get_json()["token"]
        self.device = self.app.test_client()  # the ESP32: no login, only its token

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
        self.context.pop()

    def upload(self, readings, token=None):
        return self.device.post("/api/health/readings", json={"readings": readings},
                                headers={"Authorization": f"Bearer {token or self.token}"})

    def test_token_is_stored_hashed(self):
        device = db.session.execute(db.select(HealthDevice)).scalar_one()
        self.assertNotEqual(device.token_hash, self.token)
        self.assertEqual(device.token_hash, hash_token(self.token))
        self.assertNotIn("token", str(self.bao.get("/api/health/devices").get_json()))

    def test_simulated_walk_end_to_end(self):
        r = self.upload(fake_walk(minutes=10, seed=1))
        self.assertEqual((r.status_code, r.get_json()["saved"]), (201, 120))
        data = self.bao.get("/api/health/summary").get_json()
        self.assertAlmostEqual(data["walk"]["minutes"], 10, delta=0.5)
        self.assertGreater(data["walk"]["steps"], 900)
        self.assertTrue(data["chart"])
        self.assertTrue(data["advice"])
        with patch("health_ai.requests.post", side_effect=requests.ConnectionError()):
            self.assertEqual(self.bao.post("/api/health/analyse").get_json()["source"], "StepQuest rules")

    def test_wrong_or_missing_token(self):
        self.assertEqual(self.upload([{"hr": 80}], token="nope").status_code, 401)
        self.assertEqual(self.device.post("/api/health/readings", json={"readings": [{"hr": 80}]}).status_code, 401)

    def test_bad_upload(self):
        self.assertEqual(self.upload([{"hr": 999}]).status_code, 400)

    def test_no_walk_yet(self):
        self.assertIsNone(self.bao.get("/api/health/summary").get_json()["walk"])
        self.assertEqual(self.bao.post("/api/health/analyse").status_code, 404)

    def test_resting_heart_rate_you_give_is_used(self):
        self.upload(fake_walk(minutes=5, seed=4))
        guessed = self.bao.get("/api/health/summary").get_json()["walk"]
        self.bao.post("/api/health/profile", json={"age": 20, "resting_hr": 60})
        mine = self.bao.get("/api/health/summary").get_json()["walk"]
        self.assertEqual((mine["hr_rest_estimate"], mine["hr_rest_source"]), (60, "you"))
        self.assertGreater(mine["vo2max_estimate"], guessed["vo2max_estimate"])
        self.assertEqual(self.bao.post("/api/health/profile", json={"age": 20, "resting_hr": 5}).status_code, 400)

    def test_age_changes_the_zones(self):
        self.assertEqual(self.bao.post("/api/health/profile", json={"age": 50}).get_json(),
                         {"age": 50, "resting_hr": None})
        self.upload(fake_walk(minutes=5, seed=2))
        self.assertEqual(self.bao.get("/api/health/summary").get_json()["walk"]["hr_max_for_age"], 173)
        self.assertEqual(self.bao.post("/api/health/profile", json={"age": 3}).status_code, 400)

    def test_removing_a_device_removes_its_readings(self):
        self.upload(fake_walk(minutes=2, seed=3))
        device_id = self.bao.get("/api/health/devices").get_json()["devices"][0]["id"]
        self.assertEqual(self.bao.delete(f"/api/health/devices/{device_id}").status_code, 200)
        self.assertEqual(db.session.execute(db.select(HealthReading)).scalars().all(), [])
        self.assertEqual(self.upload([{"hr": 80}]).status_code, 401)  # the old token no longer works

    def test_other_players_cannot_remove_my_device(self):
        other = self.app.test_client()
        other.post("/api/register", json={"username": "lan", "password": "secret1"})
        device_id = self.bao.get("/api/health/devices").get_json()["devices"][0]["id"]
        self.assertEqual(other.delete(f"/api/health/devices/{device_id}").status_code, 404)

    def test_page_and_login(self):
        self.assertEqual(self.bao.get("/health").status_code, 200)
        self.assertIn("/login", self.app.test_client().get("/health").headers["Location"])
        self.assertEqual(self.app.test_client().get("/api/health/summary").status_code, 401)


if __name__ == "__main__":
    unittest.main()

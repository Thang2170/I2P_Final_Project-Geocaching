"""B: the live band simulator (simulate_band.py, band_scenarios.py) does what each scenario promises.

Checked with the app's own rules (zone_coach.py, safety.py), and end to end against a test app.
Never touches the network: the simulator's "post" is pointed at Flask's test client.
"""

import unittest
from datetime import datetime, timedelta

import requests

import simulate_band
from app import create_app
from band_scenarios import EVERY_S, SCENARIOS, backfill, reading_at
from health import max_heart_rate, zone_of
from health_api import HealthDevice, hash_token
from models import User, db
from safety import check
from zone_coach import bonus_coins, bonus_seconds, warning

AGE = 20
HR_MAX = max_heart_rate(AGE)
T0 = datetime(2026, 11, 25, 9, 0)


def timed(scenario, seconds, age=AGE):
    """(time, hr, spo2) for the first `seconds` of a scenario, as the server would store them."""
    return [(T0 + timedelta(seconds=t), reading_at(scenario, t, age, seed=1)["hr"], reading_at(scenario, t, age, seed=1)["spo2"])
            for t in range(0, seconds, EVERY_S)]


class ScenarioTest(unittest.TestCase):
    def test_every_reading_is_valid_for_the_app(self):
        for name in SCENARIOS:
            for t in (0, 30, 90, 600):
                r = reading_at(name, t, seed=1)
                self.assertTrue(30 <= r["hr"] <= 230 and 50 <= r["spo2"] <= 100 and 0 <= r["steps"] <= 2000, (name, r))

    def test_unknown_scenario(self):
        with self.assertRaises(ValueError):
            reading_at("dance", 0)

    def test_zone_pays_bonus(self):
        readings = [(when, hr) for when, hr, _ in timed("zone", 9 * 60)]
        self.assertEqual(bonus_coins(bonus_seconds(readings, HR_MAX)), 3)

    def test_hard_and_maximum_warn(self):
        self.assertIn("Hard zone", warning([(w, hr) for w, hr, _ in timed("hard", 10 * 60)], HR_MAX))
        self.assertIn("Maximum", warning([(w, hr) for w, hr, _ in timed("maximum", 2 * 60)], HR_MAX))
        self.assertIsNone(warning([(w, hr) for w, hr, _ in timed("calm", 10 * 60)], HR_MAX))

    def test_cooldown_gets_gentle(self):
        hrs = [hr for _, hr, _ in timed("cooldown", 4 * 60)]
        self.assertGreaterEqual(zone_of(hrs[0], HR_MAX), 2)                  # starts in the bonus zone
        self.assertTrue(all(hr < 0.7 * HR_MAX for hr in hrs[13:]))          # easy after about a minute

    def test_safety_scenarios_stop_the_hunt(self):
        for name, reason in (("low-spo2", "low_spo2"), ("high-hr", "high_hr"), ("low-hr", "low_hr")):
            self.assertEqual(check(timed(name, 15), HR_MAX)["level"], "ok", name)  # fine at first
            self.assertEqual(check(timed(name, 60), HR_MAX)["reason"], reason, name)

    def test_zones_follow_age(self):
        old = reading_at("zone", 600, age=60, seed=1)["hr"]
        young = reading_at("zone", 600, age=20, seed=1)["hr"]
        self.assertLess(old, young)
        self.assertEqual(zone_of(old, max_heart_rate(60)), zone_of(young, max_heart_rate(20)))

    def test_backfill(self):
        earlier = backfill("hard")
        self.assertEqual(len(earlier), 10 * 60 // EVERY_S)
        self.assertEqual((earlier[0]["age_s"], earlier[-1]["age_s"]), (600, 5))  # oldest first, ending now
        self.assertEqual(backfill("low-spo2"), [])


class AgainstTheAppTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app("sqlite:///:memory:")
        self.context = self.app.app_context()
        self.context.push()
        self.client = self.app.test_client()
        self.client.post("/api/register", json={"username": "ann", "password": "secret1"})
        ann = db.session.execute(db.select(User).filter_by(username="ann")).scalar_one()
        db.session.add(HealthDevice(user_id=ann.id, name="band", token_hash=hash_token("demo-token")))
        db.session.commit()
        self.said = []

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
        self.context.pop()

    def poster(self, url, json, headers, **_):
        """Send the simulator's upload to the test app instead of the network."""
        res = self.client.post(url.split("5000", 1)[1], json=json, headers=headers)
        return type("Response", (), {"status_code": res.status_code, "text": res.get_data(as_text=True)})()

    def sim(self, *args):
        return simulate_band.main(list(args), poster=self.poster, sleep=lambda s: None, say=self.said.append)

    def test_hard_scenario_shows_the_warning_on_the_map(self):
        self.assertEqual(self.sim("hard", "--token", "demo-token", "--minutes", "0.5"), 0)
        data = self.client.get("/api/zone/now?duration_s=900").get_json()
        self.assertTrue(data["has_band"])
        self.assertIn("Hard zone", data["warning"])
        self.assertIn("Done: 126 readings sent.", self.said)  # 120 backfilled + 6 live

    def test_wrong_token(self):
        self.sim("calm", "--token", "nope", "--minutes", "0.1")
        self.assertTrue(any("doesn't know this token" in line for line in self.said))

    def test_no_token_and_list(self):
        self.assertEqual(self.sim("calm", "--token", ""), 2)
        self.assertEqual(self.sim("--list"), 0)
        self.assertTrue(any(line.startswith("low-spo2") for line in self.said))

    def test_app_not_running(self):
        def offline(*_, **__):
            raise requests.ConnectionError
        simulate_band.main(["calm", "--token", "t", "--minutes", "0.1"], poster=offline, sleep=lambda s: None,
                           say=self.said.append)
        self.assertTrue(any("Is the app running?" in line for line in self.said))


if __name__ == "__main__":
    unittest.main()

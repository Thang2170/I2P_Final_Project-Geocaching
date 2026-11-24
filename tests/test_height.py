"""B: your height sets your step length, so steps count more accurately."""

import unittest

from app import create_app
from walk_input import parse_height_cm, step_length_from_height


class HeightRulesTest(unittest.TestCase):
    def test_step_length(self):
        self.assertEqual(step_length_from_height(170), 0.706)
        self.assertEqual(step_length_from_height(150), 0.623)

    def test_height_range(self):
        self.assertEqual(parse_height_cm("172.5"), 172.5)
        for bad in (None, "", "tall", "99", "231", "-170"):
            with self.assertRaises(ValueError):
                parse_height_cm(bad)


class HeightApiTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app("sqlite:///:memory:")
        self.client = self.app.test_client()

    def login(self):
        self.client.post("/api/register", json={"username": "ann", "password": "secret1"})

    def test_must_log_in(self):
        self.assertEqual(self.client.get("/api/me/height").status_code, 401)
        self.assertEqual(self.client.post("/api/me/height", json={"height_cm": 170}).status_code, 401)

    def test_save_and_read(self):
        self.login()
        self.assertIsNone(self.client.get("/api/me/height").get_json()["height_cm"])
        res = self.client.post("/api/me/height", json={"height_cm": "160"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["step_length_m"], 0.664)
        # saving again changes it, it does not add a second row
        self.client.post("/api/me/height", data={"height_cm": "180"})
        self.assertEqual(self.client.get("/api/me/height").get_json()["height_cm"], 180)

    def test_bad_height(self):
        self.login()
        res = self.client.post("/api/me/height", json={"height_cm": "500"})
        self.assertEqual(res.status_code, 400)
        self.assertIn("height_cm", res.get_json()["error"])

    def test_steps_use_your_height(self):
        self.login()
        before = self.client.get("/api/walk-stats?distance_m=750").get_json()
        self.assertEqual(before["steps"], 1000)  # average 0.75 m step
        self.assertIsNone(before["height_cm"])
        self.client.post("/api/me/height", json={"height_cm": 150})
        after = self.client.get("/api/walk-stats?distance_m=750").get_json()
        self.assertEqual(after["steps"], round(750 / 0.623))  # shorter legs, more steps
        self.assertEqual(after["height_cm"], 150)
        self.assertEqual(after["calories"], before["calories"])  # calories do not depend on steps


if __name__ == "__main__":
    unittest.main()

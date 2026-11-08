import unittest
from unittest.mock import patch  # A: needed by test_home_page_loads

from app import app


class TestDistanceApi(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_standing_on_treasure_is_found(self):
        r = self.client.get("/api/distance?lat=24.795324&lon=120.994796")
        data = r.get_json()
        self.assertEqual(r.status_code, 200)
        self.assertEqual(data["meters"], 0)
        self.assertTrue(data["found"])

    def test_78_m_away_is_not_found(self):
        r = self.client.get("/api/distance?lat=24.7960&lon=120.9950")
        self.assertFalse(r.get_json()["found"])

    def test_bad_coordinates_return_400(self):
        r = self.client.get("/api/distance?lat=abc&lon=1")
        self.assertEqual(r.status_code, 400)

    def test_home_page_loads(self):
        # A: "/" now needs a logged-in user, so pretend someone is logged in.
        with patch("app.current_user", return_value=object()):
            self.assertEqual(self.client.get("/").status_code, 200)


if __name__ == "__main__":
    unittest.main()
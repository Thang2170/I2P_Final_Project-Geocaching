import unittest
from unittest.mock import patch  # A: needed by test_home_page_loads

from app import create_app
from models import Treasure, db


class TestDistanceApi(unittest.TestCase):
    def setUp(self):
        # B: each test gets its own throwaway in-memory database (with the NTHU demo
        # treasure), so these tests no longer depend on, or touch, instance/geohunt.db.
        self.app = create_app("sqlite:///:memory:")
        self.client = self.app.test_client()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()
            db.engine.dispose()

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

    def test_distance_to_a_chosen_treasure(self):
        with self.app.app_context():
            first = db.session.execute(db.select(Treasure).order_by(Treasure.id)).scalars().first()
            lat, lon, name = first.lat, first.lon, first.name
            first_id = first.id
        r = self.client.get(f"/api/distance?lat={lat}&lon={lon}&treasure_id={first_id}")
        data = r.get_json()
        self.assertEqual(r.status_code, 200)
        self.assertEqual(data["treasure"], name)
        self.assertTrue(data["found"])

    def test_distance_to_a_second_treasure_not_the_first(self):
        with self.app.app_context():
            second = Treasure(name="Library", lat=24.80, lon=121.00)
            db.session.add(second)
            db.session.commit()
            second_id = second.id
        r = self.client.get(f"/api/distance?lat=24.80&lon=121.00&treasure_id={second_id}")
        data = r.get_json()
        self.assertEqual(data["treasure"], "Library")
        self.assertTrue(data["found"])

    def test_unknown_treasure_id_returns_404(self):
        r = self.client.get("/api/distance?lat=24.79&lon=120.99&treasure_id=99999999")
        self.assertEqual(r.status_code, 404)

    def test_bad_treasure_id_returns_400(self):
        r = self.client.get("/api/distance?lat=24.79&lon=120.99&treasure_id=abc")
        self.assertEqual(r.status_code, 400)

    def test_home_page_loads(self):
        # A: "/" now needs a logged-in user, so pretend someone is logged in.
        with patch("app.current_user", return_value=object()):
            self.assertEqual(self.client.get("/").status_code, 200)


if __name__ == "__main__":
    unittest.main()

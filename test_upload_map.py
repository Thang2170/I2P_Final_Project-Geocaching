"""Hide a treasure by tapping the map: the spot check and the page."""

import unittest

from app import create_app
from models import DEMO_TREASURE, Treasure, db
from treasure_input import MIN_TREASURE_GAP_M, spot_problem

LAT, LON = DEMO_TREASURE["lat"], DEMO_TREASURE["lon"]  # saved on start by seed_demo_data
ABOUT_5_M = 0.000045   # degrees of latitude
ABOUT_55_M = 0.0005


class TestSpotProblem(unittest.TestCase):
    EXISTING = [("Pond", LAT, LON)]

    def test_a_free_spot_has_no_problem(self):
        self.assertIsNone(spot_problem(LAT + ABOUT_55_M, LON, self.EXISTING))

    def test_a_spot_too_close_names_the_other_treasure(self):
        problem = spot_problem(LAT + ABOUT_5_M, LON, self.EXISTING)
        self.assertIn('"Pond"', problem)
        self.assertIn(f"{MIN_TREASURE_GAP_M} m", problem)

    def test_no_treasures_yet(self):
        self.assertIsNone(spot_problem(LAT, LON, []))


class TestSpotApi(unittest.TestCase):
    def setUp(self):
        self.app = create_app("sqlite:///:memory:")
        self.context = self.app.app_context()
        self.context.push()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
        self.context.pop()

    def spot(self, lat, lon):
        return self.client.get(f"/api/treasures/spot?lat={lat}&lon={lon}")

    def test_a_free_spot(self):
        r = self.spot(LAT + ABOUT_55_M, LON)
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertTrue(data["ok"])
        self.assertEqual((data["lat"], data["lon"]), (round(LAT + ABOUT_55_M, 6), round(LON, 6)))

    def test_too_close_to_a_hidden_treasure(self):
        data = self.spot(LAT + ABOUT_5_M, LON).get_json()
        self.assertFalse(data["ok"])
        self.assertIn(DEMO_TREASURE["name"], data["message"])

    def test_the_check_and_the_upload_give_the_same_answer(self):
        self.client.post("/api/register", json={"username": "ann", "password": "secret1"})
        lat = LAT + ABOUT_5_M
        check = self.spot(lat, LON).get_json()["message"]
        upload = self.client.post("/api/treasures", json={"name": "Too close", "lat": lat, "lon": LON})
        self.assertEqual(upload.status_code, 409)
        self.assertEqual(upload.get_json()["error"], check)

    def test_bad_numbers(self):
        for query in ("lat=&lon=1", "lat=x&lon=1", "lat=95&lon=1", "lat=1&lon=200", "lon=1"):
            with self.subTest(query=query):
                self.assertEqual(self.client.get(f"/api/treasures/spot?{query}").status_code, 400)

    def test_checking_saves_nothing(self):
        before = db.session.query(Treasure).count()
        self.spot(LAT + ABOUT_55_M, LON)
        self.assertEqual(db.session.query(Treasure).count(), before)


class TestUploadPage(unittest.TestCase):
    def setUp(self):
        self.app = create_app("sqlite:///:memory:")
        self.html = self.app.test_client().get("/upload").get_data(as_text=True)

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()
            db.engine.dispose()

    def test_has_a_map_to_tap(self):
        self.assertIn('id="pickMap"', self.html)
        self.assertIn("leaflet.js", self.html)
        self.assertIn('map.on("click"', self.html)

    def test_the_coin_can_be_dragged(self):
        self.assertIn("draggable: true", self.html)
        self.assertIn('"dragend"', self.html)

    def test_python_checks_the_spot(self):
        self.assertIn("/api/treasures/spot?lat=", self.html)

    def test_shows_the_treasures_already_hidden(self):
        self.assertIn('fetch("/api/treasures")', self.html)

    def test_typing_coordinates_still_works(self):
        self.assertIn('id="lat"', self.html)
        self.assertIn('id="lon"', self.html)

    def test_never_uses_innerhtml(self):
        self.assertNotIn(".innerHTML", self.html)


if __name__ == "__main__":
    unittest.main()

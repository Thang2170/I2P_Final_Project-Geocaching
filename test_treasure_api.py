import unittest

from flask import Flask

from models import Treasure, db, seed_demo_data
from treasure_api import treasure_api


class TestTreasureApi(unittest.TestCase):
    def setUp(self):
        # A throwaway app with an in-memory database, so tests never touch geohunt.db.
        self.app = Flask(__name__)
        self.app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
        db.init_app(self.app)
        self.app.register_blueprint(treasure_api)
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
        self.context.pop()

    def post(self, **fields):
        data = {"name": "Library", "description": "Behind the bench", "lat": 24.79, "lon": 120.99}
        data.update(fields)
        return self.client.post("/api/treasures", json=data)

    def test_upload_page_loads(self):
        r = self.client.get("/upload")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"Hide a treasure", r.data)

    def test_good_upload_is_saved(self):
        r = self.post()
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.get_json()["name"], "Library")
        saved = db.session.query(Treasure).one()
        self.assertEqual((saved.name, saved.lat, saved.lon), ("Library", 24.79, 120.99))

    def test_form_data_also_works(self):
        r = self.client.post("/api/treasures", data={"name": "Gym", "lat": "24.8", "lon": "121.0"})
        self.assertEqual(r.status_code, 201)
        self.assertEqual(db.session.query(Treasure).one().name, "Gym")

    def test_bad_upload_returns_400_and_saves_nothing(self):
        for fields in [{"name": ""}, {"lat": 95}, {"lon": "abc"}, {"name": "x" * 101}]:
            with self.subTest(fields=fields):
                r = self.post(**fields)
                self.assertEqual(r.status_code, 400)
                self.assertIn("error", r.get_json())
        self.assertEqual(db.session.query(Treasure).count(), 0)

    def test_empty_body_returns_400(self):
        self.assertEqual(self.client.post("/api/treasures").status_code, 400)

    def test_list_returns_all_treasures_oldest_first(self):
        seed_demo_data()
        self.post(name="Library")
        names = [t["name"] for t in self.client.get("/api/treasures").get_json()]
        self.assertEqual(names, ["National Tsing Hua University", "Library"])


if __name__ == "__main__":
    unittest.main()

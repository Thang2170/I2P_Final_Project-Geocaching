import unittest

from flask import Flask

from auth_api import auth_api
from models import Profile, db
from walk_api import walk_api


class TestWalkApi(unittest.TestCase):
    def setUp(self):
        # A throwaway app with an in-memory database, so tests never touch geohunt.db.
        self.app = Flask(__name__)
        self.app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
        self.app.config["SECRET_KEY"] = "test-key"
        db.init_app(self.app)
        self.app.register_blueprint(auth_api)
        self.app.register_blueprint(walk_api)
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
        self.context.pop()

    def register(self, client=None):
        return (client or self.client).post("/api/register", json={"username": "bao", "password": "secret1"})

    def test_steps_and_calories_with_a_given_weight(self):
        # 750 m is 1000 steps; 1 km at 60 kg is 30 kcal (the examples in calculator.py's tests)
        data = self.client.get("/api/walk-stats?distance_m=1000&weight_kg=60").get_json()
        self.assertEqual(data["steps"], 1333)
        self.assertEqual(data["calories"], 30.0)
        self.assertEqual(data["weight_source"], "request")

    def test_750_m_is_1000_steps(self):
        self.assertEqual(self.client.get("/api/walk-stats?distance_m=750").get_json()["steps"], 1000)

    def test_default_weight_when_nothing_is_known(self):
        data = self.client.get("/api/walk-stats?distance_m=1000").get_json()
        self.assertEqual(data["weight_source"], "default")
        self.assertEqual(data["weight_kg"], 65)
        self.assertEqual(data["calories"], 32.5)

    def test_saved_weight_is_used_when_logged_in(self):
        self.register()
        self.client.post("/api/me/weight", json={"weight_kg": 80})
        data = self.client.get("/api/walk-stats?distance_m=1000").get_json()
        self.assertEqual(data["weight_source"], "profile")
        self.assertEqual(data["calories"], 40.0)

    def test_a_weight_in_the_request_beats_the_saved_one(self):
        self.register()
        self.client.post("/api/me/weight", json={"weight_kg": 80})
        data = self.client.get("/api/walk-stats?distance_m=1000&weight_kg=60").get_json()
        self.assertEqual(data["weight_source"], "request")
        self.assertEqual(data["calories"], 30.0)

    def test_zero_distance(self):
        data = self.client.get("/api/walk-stats?distance_m=0").get_json()
        self.assertEqual((data["steps"], data["calories"]), (0, 0.0))

    def test_bad_requests_return_400(self):
        for url in ["/api/walk-stats", "/api/walk-stats?distance_m=abc", "/api/walk-stats?distance_m=-5",
                    "/api/walk-stats?distance_m=1000000", "/api/walk-stats?distance_m=100&weight_kg=5",
                    "/api/walk-stats?distance_m=100&weight_kg=abc", "/api/walk-stats?distance_m=nan"]:
            with self.subTest(url=url):
                r = self.client.get(url)
                self.assertEqual(r.status_code, 400)
                self.assertIn("error", r.get_json())

    def test_weight_endpoints_need_a_login(self):
        self.assertEqual(self.client.get("/api/me/weight").status_code, 401)
        self.assertEqual(self.client.post("/api/me/weight", json={"weight_kg": 60}).status_code, 401)

    def test_nothing_saved_yet(self):
        self.register()
        data = self.client.get("/api/me/weight").get_json()
        self.assertIsNone(data["weight_kg"])
        self.assertEqual(data["default_kg"], 65)

    def test_saving_a_weight_twice_updates_it(self):
        self.register()
        self.client.post("/api/me/weight", json={"weight_kg": 70})
        r = self.client.post("/api/me/weight", json={"weight_kg": "72.5"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.client.get("/api/me/weight").get_json()["weight_kg"], 72.5)
        self.assertEqual(db.session.query(Profile).count(), 1)

    def test_bad_weights_are_refused_and_not_saved(self):
        self.register()
        for body in [{"weight_kg": 5}, {"weight_kg": "abc"}, {}, {"weight_kg": 999}]:
            with self.subTest(body=body):
                self.assertEqual(self.client.post("/api/me/weight", json=body).status_code, 400)
        self.assertEqual(db.session.query(Profile).count(), 0)

    def test_weights_belong_to_one_player(self):
        self.register()
        self.client.post("/api/me/weight", json={"weight_kg": 90})
        other = self.app.test_client()
        other.post("/api/register", json={"username": "lan", "password": "secret2"})
        self.assertIsNone(other.get("/api/me/weight").get_json()["weight_kg"])


if __name__ == "__main__":
    unittest.main()

import os
import unittest
from unittest.mock import patch

from flask import Flask

from route_api import route_api
from tests import PROJECT_ROOT


class TestRouteApi(unittest.TestCase):
    def setUp(self):
        # No API key means the offline fallback, so these tests never use the internet.
        patcher = patch.dict(os.environ)
        patcher.start()
        os.environ.pop("ORS_API_KEY", None)
        self.addCleanup(patcher.stop)

        app = Flask(__name__, root_path=PROJECT_ROOT)
        app.register_blueprint(route_api)
        self.client = app.test_client()

    def test_good_request_returns_a_route(self):
        r = self.client.get("/api/route?points=24.795324,120.994796;24.7960,120.9950")
        data = r.get_json()
        self.assertEqual(r.status_code, 200)
        self.assertAlmostEqual(data["distance_m"], 77.9, delta=1)
        self.assertEqual(len(data["path"]), 2)
        self.assertEqual(data["source"], "straight-line")
        self.assertIn("warning", data)

    def test_three_points(self):
        r = self.client.get("/api/route?points=24.7953,120.9948;24.7960,120.9950;24.7965,120.9960")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.get_json()["path"]), 3)

    def test_bad_requests_return_400(self):
        for url in [
            "/api/route",
            "/api/route?points=",
            "/api/route?points=24.79,120.99",
            "/api/route?points=abc;def",
            "/api/route?points=95,0;0,0",
        ]:
            with self.subTest(url=url):
                r = self.client.get(url)
                self.assertEqual(r.status_code, 400)
                self.assertIn("error", r.get_json())

    # ---------------------------------------------------- random routes (Feature 6)

    def test_random_route_goes_through_a_side_step_point(self):
        r = self.client.get("/api/random-route?points=24.795324,120.994796;24.8040,120.9948")
        data = r.get_json()
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(data["path"]), 3)
        self.assertEqual(data["path"][1], data["via"])

    def test_same_treasure_gets_different_routes(self):
        url = "/api/random-route?points=24.795324,120.994796;24.8040,120.9948"
        vias = {tuple(self.client.get(url).get_json()["via"]) for _ in range(5)}
        self.assertGreater(len(vias), 1)

    def test_random_route_bad_requests_return_400(self):
        for url in [
            "/api/random-route",
            "/api/random-route?points=24.79,120.99",
            "/api/random-route?points=24.7953,120.9948;24.7960,120.9950;24.7965,120.9960",
            "/api/random-route?points=24.795324,120.994796;24.795324,120.994796",  # already there
        ]:
            with self.subTest(url=url):
                r = self.client.get(url)
                self.assertEqual(r.status_code, 400)
                self.assertIn("error", r.get_json())

    def test_reached_side_step_point_is_dropped(self):
        # The middle point is about 8 m from where you are: you got there
        r = self.client.get("/api/route?points=24.795324,120.994796;24.795400,120.994800;24.8040,120.9948")
        data = r.get_json()
        self.assertTrue(data["via_reached"])
        self.assertEqual(len(data["path"]), 2)

    def test_side_step_point_not_reached_is_kept(self):
        r = self.client.get("/api/route?points=24.795324,120.994796;24.7960,120.9950;24.8040,120.9948")
        data = r.get_json()
        self.assertNotIn("via_reached", data)
        self.assertEqual(len(data["path"]), 3)


if __name__ == "__main__":
    unittest.main()
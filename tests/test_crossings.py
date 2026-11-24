import os
import unittest
from unittest.mock import Mock, patch

import requests
from flask import Flask

import crossings
import route_api
from crossings import (CrossingError, bounding_box, check_path, crossings_on_route, distance_to_segment_m,
                       fetch_crossings, kind_of, overpass_query, parse_crossings, warning_for)
from route_api import route_api as route_blueprint
from tests import PROJECT_ROOT

# A short north-south walk on campus, and a crossing right on it / far off it
PATH = [[24.7940, 120.9950], [24.7950, 120.9950], [24.7960, 120.9950]]
ON = {"id": 1, "lat": 24.7950, "lon": 120.99505, "kind": "zebra crossing"}    # about 5 m east of the path
OFF = {"id": 2, "lat": 24.7950, "lon": 120.9960, "kind": "street crossing"}   # about 100 m east


def overpass_answer(status=200, elements=None):
    response = Mock()
    response.status_code = status
    response.json.return_value = {"elements": elements or []}
    return response


ELEMENTS = [
    {"type": "node", "id": 1, "lat": ON["lat"], "lon": ON["lon"], "tags": {"highway": "crossing", "crossing": "zebra"}},
    {"type": "node", "id": 2, "lat": OFF["lat"], "lon": OFF["lon"], "tags": {"highway": "crossing"}},
    {"type": "node", "id": 3, "lat": 24.7955, "lon": 120.9950, "tags": {"railway": "crossing"}},
]


class TestGeometry(unittest.TestCase):
    def test_distance_to_a_segment(self):
        a, b = (24.7940, 120.9950), (24.7960, 120.9950)
        self.assertAlmostEqual(distance_to_segment_m((24.7950, 120.9950), a, b), 0, delta=0.5)
        self.assertAlmostEqual(distance_to_segment_m((24.7950, 120.99505), a, b), 5.1, delta=0.5)
        # past the end of the segment: measured to the end point, not to the endless line
        self.assertAlmostEqual(distance_to_segment_m((24.7970, 120.9950), a, b), 111, delta=2)

    def test_only_crossings_on_the_route_are_kept(self):
        self.assertEqual(crossings_on_route(check_path(PATH), [ON, OFF]), [ON])

    def test_bounding_box_has_a_margin(self):
        south, west, north, east = bounding_box(check_path(PATH))
        self.assertLess(south, 24.7940)
        self.assertGreater(north, 24.7960)
        self.assertLess(west, 120.9950)
        self.assertGreater(east, 120.9950)

    def test_bad_paths(self):
        for bad in [None, [], [[1, 2]], [["a", 2], [1, 2]], [[95, 0], [0, 0]]]:
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    check_path(bad)


class TestWarnings(unittest.TestCase):
    def test_warn_within_20_m(self):
        w = warning_for(24.79515, 120.99505, [ON, OFF])  # about 17 m north of ON
        self.assertEqual((w["id"], w["kind"]), (1, "zebra crossing"))
        self.assertIn("look up", w["text"])
        self.assertLessEqual(w["distance_m"], 20)

    def test_no_warning_far_away(self):
        self.assertIsNone(warning_for(24.7930, 120.9950, [ON, OFF]))

    def test_nearest_crossing_wins(self):
        near = dict(ON, id=9, lat=24.79502)
        self.assertEqual(warning_for(24.79502, 120.99505, [ON, near])["id"], 9)

    def test_kinds(self):
        self.assertEqual(kind_of({"crossing": "traffic_signals"}), "crossing with traffic lights")
        self.assertEqual(kind_of({"railway": "crossing"}), "railway crossing")
        self.assertEqual(kind_of({}), "street crossing")

    def test_parse_crossings(self):
        self.assertEqual(parse_crossings([{"id": "1", "lat": "24.79", "lon": 120.99}])[0]["id"], 1)
        for bad in [None, "x", [{"lat": 1}], [{"id": 1, "lat": "a", "lon": 1}]]:
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    parse_crossings(bad)


class TestOverpass(unittest.TestCase):
    def test_query_asks_for_crossings_in_the_box(self):
        q = overpass_query((24.79, 120.99, 24.80, 121.00))
        self.assertIn('node["highway"="crossing"](24.790000,120.990000,24.800000,121.000000)', q)
        self.assertIn("[out:json]", q)

    def test_reads_the_answer(self):
        with patch("crossings.requests.post", return_value=overpass_answer(elements=ELEMENTS)) as post:
            found = fetch_crossings(check_path(PATH))
        self.assertEqual([c["id"] for c in found], [1, 2, 3])
        self.assertEqual(found[0]["kind"], "zebra crossing")
        self.assertIn("User-Agent", post.call_args.kwargs["headers"])  # Overpass refuses requests without it

    def test_busy_server_falls_back_to_a_mirror(self):
        answers = [overpass_answer(status=504), overpass_answer(elements=ELEMENTS)]
        with patch("crossings.requests.post", side_effect=answers) as post:
            found = fetch_crossings(check_path(PATH))
        self.assertEqual(len(found), 3)
        self.assertEqual(post.call_count, 2)

    def test_every_server_down_raises(self):
        with patch("crossings.requests.post", side_effect=requests.ReadTimeout()):
            with self.assertRaises(CrossingError):
                fetch_crossings(check_path(PATH))


class TestCrossingApi(unittest.TestCase):
    def setUp(self):
        app = Flask(__name__, root_path=PROJECT_ROOT)
        app.register_blueprint(route_blueprint)
        self.client = app.test_client()
        route_api._crossing_cache.clear()
        route_api._overpass_down_until = 0.0
        self.addCleanup(route_api._crossing_cache.clear)

    def test_route_crossings(self):
        with patch("crossings.requests.post", return_value=overpass_answer(elements=ELEMENTS)):
            data = self.client.post("/api/crossings", json={"path": PATH}).get_json()
        self.assertEqual(data["source"], "openstreetmap")
        self.assertEqual({c["id"] for c in data["crossings"]}, {1, 3})  # 2 is off the route

    def test_same_area_is_asked_only_once(self):
        with patch("crossings.requests.post", return_value=overpass_answer(elements=ELEMENTS)) as post:
            self.client.post("/api/crossings", json={"path": PATH})
            self.client.post("/api/crossings", json={"path": PATH})
        self.assertEqual(post.call_count, 1)

    def test_openstreetmap_down_still_answers(self):
        with patch("crossings.requests.post", side_effect=requests.ConnectionError()):
            r = self.client.post("/api/crossings", json={"path": PATH})
        data = r.get_json()
        self.assertEqual((r.status_code, data["crossings"], data["source"]), (200, [], "unavailable"))
        self.assertIn("No crossing warnings", data["warning"])

    def test_after_a_failure_overpass_is_not_asked_again_for_a_while(self):
        with patch("crossings.requests.post", side_effect=requests.ConnectionError()) as post:
            self.client.post("/api/crossings", json={"path": PATH})
            calls = post.call_count
            other = [[24.80, 121.0], [24.801, 121.0]]  # a different area: not in the cache
            data = self.client.post("/api/crossings", json={"path": other}).get_json()
        self.assertEqual(post.call_count, calls)  # no new requests: players don't wait again
        self.assertEqual(data["source"], "unavailable")

    def test_warning_endpoint(self):
        r = self.client.post("/api/crossings/warning", json={"lat": 24.79515, "lon": 120.99505, "crossings": [ON]})
        self.assertEqual(r.get_json()["warning"]["id"], 1)
        r = self.client.post("/api/crossings/warning", json={"lat": 24.7930, "lon": 120.9950, "crossings": [ON]})
        self.assertIsNone(r.get_json()["warning"])

    def test_bad_requests(self):
        self.assertEqual(self.client.post("/api/crossings", json={"path": [[1, 2]]}).status_code, 400)
        self.assertEqual(self.client.post("/api/crossings", json=None).status_code, 400)
        self.assertEqual(self.client.post("/api/crossings/warning", json={"lat": 1}).status_code, 400)


if __name__ == "__main__":
    unittest.main()


class TestManualCrossings(unittest.TestCase):
    """Crossings an admin adds by hand (the fallback when OpenStreetMap is down)."""

    def setUp(self):
        from app import create_app
        from models import db
        self.db = db
        self.env = patch.dict(os.environ, {"ADMIN_USERS": "admin"})
        self.env.start()
        self.app = create_app("sqlite:///:memory:")
        self.context = self.app.app_context()
        self.context.push()
        self.admin = self.app.test_client()
        self.admin.post("/api/register", json={"username": "admin", "password": "secret1"})
        self.player = self.app.test_client()
        self.player.post("/api/register", json={"username": "bao", "password": "secret1"})
        route_api._crossing_cache.clear()
        route_api._overpass_down_until = 0.0

    def tearDown(self):
        self.db.session.remove()
        self.db.drop_all()
        self.db.engine.dispose()
        self.context.pop()
        self.env.stop()
        route_api._crossing_cache.clear()

    def add(self, client, **body):
        return client.post("/api/admin/crossings", json={"lat": 24.7950, "lon": 120.99505, **body})

    def test_admin_adds_and_removes_a_crossing(self):
        r = self.add(self.admin, kind="zebra crossing")
        self.assertEqual(r.status_code, 201)
        crossing = r.get_json()
        self.assertLess(crossing["id"], 0)  # never clashes with OpenStreetMap ids
        self.assertEqual(self.admin.get("/api/admin/summary").get_json()["crossings"], [crossing])
        self.assertEqual(self.admin.delete(f"/api/admin/crossings/{crossing['id']}").status_code, 200)
        self.assertEqual(self.admin.get("/api/admin/summary").get_json()["crossings"], [])

    def test_players_cannot_add(self):
        self.assertEqual(self.add(self.player).status_code, 403)
        self.assertEqual(self.add(self.app.test_client()).status_code, 401)

    def test_bad_crossings(self):
        self.assertEqual(self.add(self.admin, kind="volcano").status_code, 400)
        self.assertEqual(self.admin.post("/api/admin/crossings", json={"lat": "x"}).status_code, 400)
        self.assertEqual(self.admin.delete("/api/admin/crossings/-99").status_code, 404)

    def test_hand_added_crossings_warn_even_when_openstreetmap_is_down(self):
        self.add(self.admin, kind="zebra crossing")
        with patch("crossings.requests.post", side_effect=requests.ConnectionError()):
            data = self.player.post("/api/crossings", json={"path": PATH}).get_json()
        self.assertEqual(data["source"], "stepquest")
        self.assertEqual([c["kind"] for c in data["crossings"]], ["zebra crossing"])

    def test_both_kinds_are_merged(self):
        self.add(self.admin)
        with patch("crossings.requests.post", return_value=overpass_answer(elements=ELEMENTS)):
            data = self.player.post("/api/crossings", json={"path": PATH}).get_json()
        self.assertEqual(len(data["crossings"]), 3)  # 1 by hand + 2 from OpenStreetMap on the route

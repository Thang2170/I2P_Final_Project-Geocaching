import os
import unittest
from unittest.mock import Mock, patch

import requests

from routing import (
    MAX_POINTS,
    RoutingError,
    check_point,
    get_route,
    get_walking_route,
    parse_points,
    straight_line_route,
)

NTHU = (24.795324, 120.994796)
NEARBY = (24.7960, 120.9950)  # about 78 m from NTHU

GOOD_PAYLOAD = {
    "features": [
        {
            "properties": {"summary": {"distance": 123.456, "duration": 88.4}},
            "geometry": {
                "type": "LineString",
                # ORS sends [lon, lat]
                "coordinates": [[120.994796, 24.795324], [120.9950, 24.7960]],
            },
        }
    ]
}


def fake_response(status=200, payload=None, text=""):
    response = Mock()
    response.status_code = status
    response.json.return_value = payload
    response.text = text
    return response


class NoKeyMixin:
    """Make sure no real API key is used, so no test touches the internet."""

    def setUp(self):
        patcher = patch.dict(os.environ)
        patcher.start()
        os.environ.pop("ORS_API_KEY", None)
        self.addCleanup(patcher.stop)


class TestCheckAndParse(unittest.TestCase):
    def test_check_point_accepts_numbers_and_strings(self):
        self.assertEqual(check_point((24.8, 121.0)), (24.8, 121.0))
        self.assertEqual(check_point(("24.8", "121.0")), (24.8, 121.0))

    def test_check_point_rejects_bad_values(self):
        for bad in [("abc", 1), (91, 0), (0, 181), (float("nan"), 0), (1,), None]:
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    check_point(bad)

    def test_parse_points(self):
        points = parse_points("24.795324,120.994796; 24.796,120.995")
        self.assertEqual(points, [(24.795324, 120.994796), (24.796, 120.995)])

    def test_parse_points_rejects_bad_text(self):
        for bad in ["", None, "24.79,120.99", "a,b;c,d", "1,2,3;4,5", "95,0;0,0"]:
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    parse_points(bad)

    def test_parse_points_rejects_too_many(self):
        text = ";".join(["24.79,120.99"] * (MAX_POINTS + 1))
        with self.assertRaises(ValueError):
            parse_points(text)


class TestStraightLineRoute(unittest.TestCase):
    def test_one_leg(self):
        route = straight_line_route([(0, 0), (1, 0)])
        self.assertAlmostEqual(route["distance_m"], 111_195, delta=100)
        self.assertEqual(route["source"], "straight-line")

    def test_two_legs_add_up(self):
        leg1 = straight_line_route([NTHU, NEARBY])["distance_m"]
        leg2 = straight_line_route([NEARBY, NTHU])["distance_m"]
        both = straight_line_route([NTHU, NEARBY, NTHU])["distance_m"]
        self.assertAlmostEqual(both, leg1 + leg2, delta=0.2)

    def test_path_is_lat_lon_in_order(self):
        route = straight_line_route([NTHU, NEARBY])
        self.assertEqual(route["path"], [[24.795324, 120.994796], [24.796, 120.995]])

    def test_duration_uses_walking_speed(self):
        route = straight_line_route([(0, 0), (1, 0)])
        self.assertAlmostEqual(route["duration_s"], 111_195 / 1.4, delta=100)

    def test_needs_two_points(self):
        for bad in [[], [NTHU]]:
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    straight_line_route(bad)


class TestGetWalkingRoute(NoKeyMixin, unittest.TestCase):
    def test_parses_a_good_response(self):
        with patch("routing.requests.post", return_value=fake_response(payload=GOOD_PAYLOAD)):
            route = get_walking_route([NTHU, NEARBY], api_key="test-key")
        self.assertEqual(route["distance_m"], 123.5)
        self.assertEqual(route["duration_s"], 88)
        self.assertEqual(route["path"], [[24.795324, 120.994796], [24.796, 120.995]])
        self.assertEqual(route["source"], "openrouteservice")

    def test_sends_lon_before_lat_and_the_key(self):
        with patch("routing.requests.post", return_value=fake_response(payload=GOOD_PAYLOAD)) as post:
            get_walking_route([NTHU, NEARBY], api_key="test-key")
        kwargs = post.call_args.kwargs
        self.assertEqual(kwargs["json"]["coordinates"][0], [120.994796, 24.795324])
        self.assertEqual(kwargs["headers"]["Authorization"], "test-key")
        self.assertIn("timeout", kwargs)

    def test_missing_key_raises(self):
        with self.assertRaises(RoutingError):
            get_walking_route([NTHU, NEARBY])

    def test_http_error_raises_with_message(self):
        payload = {"error": {"code": 2010, "message": "Could not find routable point"}}
        with patch("routing.requests.post", return_value=fake_response(404, payload)):
            with self.assertRaises(RoutingError) as ctx:
                get_walking_route([NTHU, NEARBY], api_key="k")
        self.assertIn("404", str(ctx.exception))
        self.assertIn("routable point", str(ctx.exception))

    def test_network_failure_raises(self):
        with patch("routing.requests.post", side_effect=requests.ConnectionError("down")):
            with self.assertRaises(RoutingError):
                get_walking_route([NTHU, NEARBY], api_key="k")

    def test_unexpected_response_raises(self):
        with patch("routing.requests.post", return_value=fake_response(payload={"oops": 1})):
            with self.assertRaises(RoutingError):
                get_walking_route([NTHU, NEARBY], api_key="k")

    def test_key_never_appears_in_error(self):
        with patch("routing.requests.post", return_value=fake_response(403, {"error": "denied"})):
            with self.assertRaises(RoutingError) as ctx:
                get_walking_route([NTHU, NEARBY], api_key="secret-key-123")
        self.assertNotIn("secret-key-123", str(ctx.exception))


class TestGetRoute(NoKeyMixin, unittest.TestCase):
    def test_falls_back_to_straight_lines_without_key(self):
        route = get_route([NTHU, NEARBY])
        self.assertEqual(route["source"], "straight-line")
        self.assertIn("warning", route)

    def test_uses_real_route_when_available(self):
        os.environ["ORS_API_KEY"] = "test-key"
        with patch("routing.requests.post", return_value=fake_response(payload=GOOD_PAYLOAD)):
            route = get_route([NTHU, NEARBY])
        self.assertEqual(route["source"], "openrouteservice")
        self.assertNotIn("warning", route)

    def test_falls_back_when_service_fails(self):
        os.environ["ORS_API_KEY"] = "test-key"
        with patch("routing.requests.post", side_effect=requests.Timeout()):
            route = get_route([NTHU, NEARBY])
        self.assertEqual(route["source"], "straight-line")
        self.assertIn("warning", route)

    def test_bad_input_is_not_hidden_by_the_fallback(self):
        with self.assertRaises(ValueError):
            get_route([NTHU])


if __name__ == "__main__":
    unittest.main()
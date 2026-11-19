import math
import os
import random
import unittest

import routing
from unittest.mock import Mock, patch

import requests

from location import haversine_m
from routing import (
    MAX_DETOUR_M,
    MAX_POINTS,
    MIN_DETOUR_M,
    RoutingError,
    check_point,
    drop_reached_via,
    get_random_route,
    get_route,
    get_walking_route,
    parse_points,
    random_via_point,
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


class TestRoutingAddress(unittest.TestCase):
    def test_uses_the_new_heigit_address(self):
        # api.openrouteservice.org was shut down in November 2026; same paths, new host.
        self.assertTrue(routing.ORS_URL.startswith("https://api.heigit.org/openrouteservice/v2/directions/"))
        self.assertNotIn("api.openrouteservice.org", routing.ORS_URL)


# ------------------------------------------------------------ random routes (Feature 6)

FAR = (24.8040, 120.9948)  # about 965 m north of NTHU


def flat_metres(start, point):
    """(north, east) of point from start in metres, the same flat-map maths as routing.py."""
    north = (point[0] - start[0]) * 111_320
    east = (point[1] - start[1]) * 111_320 * math.cos(math.radians(start[0]))
    return north, east


def sideways_and_along(start, end, point):
    """How far point is from the start-end line (metres), and how far along it (0 to 1)."""
    line_n, line_e = flat_metres(start, end)
    p_n, p_e = flat_metres(start, point)
    length = math.hypot(line_n, line_e)
    sideways = abs(line_n * p_e - line_e * p_n) / length
    along = (line_n * p_n + line_e * p_e) / length ** 2
    return sideways, along


class TestRandomViaPoint(unittest.TestCase):
    def test_point_is_beside_the_line_within_limits(self):
        # A short trip (78 m) and a long one (965 m): the 40 m minimum and 300 m maximum both apply
        for end in (NEARBY, FAR):
            for seed in range(50):
                with self.subTest(end=end, seed=seed):
                    via = random_via_point(NTHU, end, random.Random(seed))
                    sideways, along = sideways_and_along(NTHU, end, via)
                    self.assertGreaterEqual(sideways, MIN_DETOUR_M - 1)  # 1 m for rounding
                    self.assertLessEqual(sideways, MAX_DETOUR_M + 1)
                    self.assertGreaterEqual(along, 0.3 - 0.01)
                    self.assertLessEqual(along, 0.7 + 0.01)

    def test_same_seed_gives_the_same_point(self):
        self.assertEqual(
            random_via_point(NTHU, FAR, random.Random(7)),
            random_via_point(NTHU, FAR, random.Random(7)),
        )

    def test_different_seeds_give_different_points(self):
        points = {random_via_point(NTHU, FAR, random.Random(seed)) for seed in range(10)}
        self.assertEqual(len(points), 10)

    def test_both_sides_of_the_line_are_used(self):
        # Walking north, the left side is west (smaller lon) and the right side is east.
        sides = {random_via_point(NTHU, FAR, random.Random(seed))[1] > NTHU[1] for seed in range(20)}
        self.assertEqual(sides, {True, False})

    def test_already_at_the_treasure(self):
        with self.assertRaises(ValueError):
            random_via_point(NTHU, (24.795330, 120.994800))  # under 1 m away

    def test_bad_point(self):
        with self.assertRaises(ValueError):
            random_via_point(("abc", 1), NTHU)


class TestGetRandomRoute(NoKeyMixin, unittest.TestCase):
    def test_no_key_gives_straight_lines_through_the_point(self):
        route = get_random_route(NTHU, FAR, random.Random(1))
        self.assertEqual(route["source"], "straight-line")
        self.assertIn("warning", route)
        self.assertEqual(len(route["path"]), 3)  # start, side-step point, treasure
        self.assertEqual(route["path"][1], route["via"])
        # Going through the side-step point is longer than the straight line
        self.assertGreater(route["distance_m"], haversine_m(*NTHU, *FAR))

    def test_with_key_asks_the_service_for_three_points(self):
        os.environ["ORS_API_KEY"] = "test-key"
        with patch("routing.requests.post", return_value=fake_response(payload=GOOD_PAYLOAD)) as post:
            route = get_random_route(NTHU, FAR, random.Random(1))
        sent = post.call_args.kwargs["json"]["coordinates"]
        self.assertEqual(len(sent), 3)
        self.assertEqual(sent[1], [route["via"][1], route["via"][0]])  # ORS wants [lon, lat]
        self.assertEqual(route["source"], "openrouteservice")


class TestDropReachedVia(unittest.TestCase):
    def test_keeps_a_point_not_reached_yet(self):
        points = [NTHU, NEARBY, FAR]  # NEARBY is 78 m away
        self.assertEqual(drop_reached_via(points), points)

    def test_drops_a_point_within_20_m(self):
        close = (24.795400, 120.994800)  # about 8 m from NTHU
        self.assertEqual(drop_reached_via([NTHU, close, FAR]), [NTHU, FAR])

    def test_two_points_stay_the_same(self):
        self.assertEqual(drop_reached_via([NTHU, FAR]), [NTHU, FAR])


if __name__ == "__main__":
    unittest.main()
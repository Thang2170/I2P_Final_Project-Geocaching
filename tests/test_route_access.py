"""B: step-free (wheelchair) routes (route_access.py, route_access_api.py). Never calls the real ORS."""

import os
import unittest
from unittest.mock import MagicMock, patch

from app import create_app
from models import RouteAccess, db
from route_access import (WALKING, WHEELCHAIR, WHEELCHAIR_LIMITS, ors_profile, parse_choice, route_extra,
                          route_note)
from routing import ORS_URL, RoutingError, get_route, ors_url

A, B = (24.7955, 120.9965), (24.7953, 120.9948)
GEOJSON = {"features": [{"properties": {"summary": {"distance": 210.0, "duration": 180.0}},
                         "geometry": {"coordinates": [[A[1], A[0]], [B[1], B[0]]]}}]}


def ors_reply():
    reply = MagicMock(status_code=200)
    reply.json.return_value = GEOJSON
    return reply


class AccessRulesTest(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(parse_choice({"access": "wheelchair"}), WHEELCHAIR)
        for bad in ({}, {"access": "car"}, "wheelchair", None):
            with self.assertRaises(ValueError):
                parse_choice(bad)

    def test_profiles_and_addresses(self):
        self.assertEqual(ors_profile(WALKING), "foot-walking")
        self.assertEqual(ors_profile(WHEELCHAIR), "wheelchair")
        self.assertEqual(ors_profile("??"), "foot-walking")
        self.assertEqual(ors_url(), ORS_URL)
        self.assertEqual(ors_url("wheelchair"), "https://api.heigit.org/openrouteservice/v2/directions/wheelchair/geojson")

    def test_extra_settings(self):
        green = {"options": {"profile_params": {"weightings": {"green": 1.0}}}}
        self.assertIsNone(route_extra(WALKING, {}))
        self.assertEqual(route_extra(WALKING, green), green)  # walking keeps the weather's settings
        chair = route_extra(WHEELCHAIR, green)
        self.assertEqual(chair, {"options": {"profile_params": {"restrictions": WHEELCHAIR_LIMITS}}})  # no "green"
        self.assertEqual(route_extra(WHEELCHAIR, {"preference": "shortest"})["preference"], "shortest")

    def test_notes(self):
        self.assertEqual(route_note(WALKING, True), "")
        self.assertIn("Step-free route", route_note(WHEELCHAIR, True))
        self.assertIn("may cross steps", route_note(WHEELCHAIR, False))


class StepFreeRoutingTest(unittest.TestCase):
    def test_a_wheelchair_route_never_falls_back_to_walking(self):
        asked = []

        def fake(points, api_key=None, extra=None, profile="foot-walking"):
            asked.append((profile, extra))
            raise RoutingError("down")
        with patch("routing._ask_service", side_effect=fake):
            route = get_route([A, B], extra={"x": 1}, profile="wheelchair")
        self.assertEqual([p for p, _ in asked], ["wheelchair", "wheelchair"])  # with, then without the extras
        self.assertIn("straight lines", route["warning"])


class AccessApiTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app("sqlite:///:memory:")
        self.ctx = self.app.app_context()
        self.ctx.push()
        self.ann = self.app.test_client()
        self.ann.post("/api/register", json={"username": "ann", "password": "secret1"})

    def tearDown(self):
        db.session.remove()
        self.ctx.pop()

    def test_choose_and_change(self):
        self.assertEqual(self.app.test_client().get("/api/me/route-access").status_code, 401)
        self.assertEqual(self.ann.get("/api/me/route-access").get_json()["access"], WALKING)
        self.assertEqual(self.ann.post("/api/me/route-access", json={"access": "car"}).status_code, 400)
        self.assertEqual(self.ann.post("/api/me/route-access", json={"access": WHEELCHAIR}).get_json()["access"], WHEELCHAIR)
        self.assertEqual(db.session.query(RouteAccess).count(), 1)
        self.ann.post("/api/me/route-access", json={"access": WALKING})
        self.assertEqual(db.session.query(RouteAccess).count(), 0)  # walking is the default: no row
        choices = self.ann.get("/api/me/route-access").get_json()["choices"]
        self.assertEqual([c["id"] for c in choices], [WALKING, WHEELCHAIR])

    def test_the_account_page_has_the_choice(self):
        self.assertIn('id="accessBox"', self.ann.get("/login").get_data(as_text=True))

    def route(self, path="/api/route"):
        with patch.dict(os.environ, {"ORS_API_KEY": "test-key"}), \
                patch("routing.requests.post", return_value=ors_reply()) as post:
            res = self.ann.get(f"{path}?points={A[0]},{A[1]};{B[0]},{B[1]}")
        return res.get_json(), post

    def test_walkers_get_the_normal_route(self):
        data, post = self.route()
        self.assertEqual(post.call_args.args[0], ORS_URL)
        self.assertNotIn("access", data)

    def test_step_free_players_get_the_wheelchair_profile(self):
        self.ann.post("/api/me/route-access", json={"access": WHEELCHAIR})
        data, post = self.route()
        self.assertTrue(post.call_args.args[0].endswith("/wheelchair/geojson"))
        self.assertEqual(post.call_args.kwargs["json"]["options"]["profile_params"]["restrictions"], WHEELCHAIR_LIMITS)
        self.assertEqual(data["access"]["choice"], WHEELCHAIR)
        self.assertIn("Step-free route", data["access"]["note"])

    def test_new_route_stays_step_free(self):
        self.ann.post("/api/me/route-access", json={"access": WHEELCHAIR})
        data, post = self.route("/api/random-route")
        self.assertTrue(all(c.args[0].endswith("/wheelchair/geojson") for c in post.call_args_list))
        self.assertEqual(data["access"]["choice"], WHEELCHAIR)

    def test_no_service_means_a_warning_not_steps(self):
        self.ann.post("/api/me/route-access", json={"access": WHEELCHAIR})
        with patch("routing._ask_service", side_effect=RoutingError("no key")):
            data = self.ann.get(f"/api/route?points={A[0]},{A[1]};{B[0]},{B[1]}").get_json()
        self.assertIn("may cross steps", data["access"]["note"])


if __name__ == "__main__":
    unittest.main()

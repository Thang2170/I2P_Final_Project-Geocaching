"""B: rain and night treasures (conditions.py, condition_api.py). Never calls the real weather service."""

import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from app import create_app
from conditions import (ALWAYS, NIGHT, RAIN, board_text, hidden_text, is_dark, is_raining, is_visible,
                        parse_condition, saved_text, sun_elevation)
from models import TreasureCondition, db

HSINCHU = (24.7955, 120.9965)
NOON = datetime(2026, 11, 26, 4, 0, tzinfo=timezone.utc)       # 12:00 in Taiwan
EVENING = datetime(2026, 11, 26, 12, 0, tzinfo=timezone.utc)    # 20:00 in Taiwan
DUSK = datetime(2026, 11, 26, 9, 10, tzinfo=timezone.utc)       # 17:10, just after sunset
SPOT = {"lat": 24.7900, "lon": 120.9900}
RAINY = ({"rain_mm": 1.2, "code": 61}, {"route_options": {}})
DRY = ({"rain_mm": 0, "code": 1}, {"route_options": {}})


class ConditionRulesTest(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(parse_condition(None), ALWAYS)
        self.assertEqual(parse_condition(""), ALWAYS)
        self.assertEqual(parse_condition(" Night "), NIGHT)
        for bad in ("snow", 3, ["rain"]):
            with self.assertRaises(ValueError):
                parse_condition(bad)

    def test_the_sun_in_hsinchu(self):
        self.assertGreater(sun_elevation(*HSINCHU, NOON), 40)        # high at noon in late November
        self.assertLess(sun_elevation(*HSINCHU, EVENING), -30)       # well down at 8 p.m.
        self.assertFalse(is_dark(*HSINCHU, NOON))
        self.assertTrue(is_dark(*HSINCHU, EVENING))
        self.assertFalse(is_dark(*HSINCHU, DUSK))  # sunset was about 17:05: still twilight

    def test_naive_times_are_utc(self):
        self.assertAlmostEqual(sun_elevation(*HSINCHU, NOON.replace(tzinfo=None)), sun_elevation(*HSINCHU, NOON))

    def test_rain(self):
        self.assertFalse(is_raining(None))  # no weather (offline, tests): not raining
        self.assertTrue(is_raining(RAINY[0]))
        self.assertTrue(is_raining({"rain_mm": 0, "code": 80}))
        self.assertFalse(is_raining(DRY[0]))

    def test_visible(self):
        self.assertTrue(is_visible(ALWAYS, False, False))
        self.assertTrue(is_visible(RAIN, True, False))
        self.assertFalse(is_visible(RAIN, False, True))
        self.assertTrue(is_visible(NIGHT, False, True))
        self.assertFalse(is_visible(NIGHT, True, False))

    def test_texts(self):
        self.assertEqual(board_text(ALWAYS, True, False), "")
        self.assertIn("Night treasure", board_text(NIGHT, True, False))
        self.assertIn("you can, because you hid it", board_text(RAIN, False, True))
        self.assertEqual(saved_text(ALWAYS), "")
        self.assertIn("after dark", saved_text(NIGHT))
        self.assertIn("in the rain", hidden_text(RAIN))
        with self.assertRaises(ValueError):
            hidden_text(ALWAYS)


class ConditionApiTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app("sqlite:///:memory:")
        self.ctx = self.app.app_context()
        self.ctx.push()
        self.owner = self.client("olga")
        self.ann = self.client("ann")

    def tearDown(self):
        db.session.remove()
        self.ctx.pop()

    def client(self, name):
        c = self.app.test_client()
        c.post("/api/register", json={"username": name, "password": "secret1"})
        return c

    def hide(self, appears, **where):
        res = self.owner.post("/api/treasures", json={"name": f"T {appears}", **(where or SPOT), "appears": appears})
        return res

    def names(self, client):
        return {t["name"]: t for t in client.get("/api/treasures").get_json()}

    def test_upload_saves_the_condition(self):
        res = self.hide(NIGHT)
        self.assertEqual(res.status_code, 201)
        self.assertIn("after dark", res.get_json()["appears_note"])
        self.assertEqual(db.session.get(TreasureCondition, res.get_json()["id"]).condition, NIGHT)
        plain = self.owner.post("/api/treasures", json={"name": "Plain", "lat": 24.791, "lon": 120.991})
        self.assertEqual(plain.get_json()["appears_note"], "")
        self.assertEqual(db.session.query(TreasureCondition).count(), 1)  # nothing saved for "always"
        self.assertEqual(self.owner.post("/api/treasures", json={"name": "X", "lat": 24.792, "lon": 120.992,
                                                                 "appears": "snow"}).status_code, 400)

    def test_the_upload_page_offers_the_choice(self):
        html = self.owner.get("/upload").get_data(as_text=True)
        self.assertIn('<option value="night">Only after dark</option>', html)

    def test_a_night_treasure_shows_only_after_dark(self):
        tid = self.hide(NIGHT).get_json()["id"]
        with patch("condition_api._now", return_value=NOON):
            self.assertNotIn("T night", self.names(self.ann))
            mine = self.names(self.owner)["T night"]  # the owner always sees it, with a note
            self.assertIn("Other players can't see it", mine["appears"]["text"])
            res = self.ann.post(f"/api/treasures/{tid}/claim", json=SPOT)
            self.assertEqual(res.status_code, 409)
            self.assertIn("after dark", res.get_json()["error"])
        with patch("condition_api._now", return_value=EVENING):
            seen = self.names(self.ann)["T night"]
            self.assertEqual(seen["appears"]["condition"], NIGHT)
            self.assertEqual(self.ann.post(f"/api/treasures/{tid}/claim", json=SPOT).status_code, 200)

    def test_a_rain_treasure_shows_only_in_the_rain(self):
        self.hide(RAIN)
        self.assertNotIn("T rain", self.names(self.ann))  # tests have no weather: not raining
        with patch("condition_api.weather_for", return_value=RAINY):
            self.assertIn("T rain", self.names(self.ann))
        with patch("condition_api.weather_for", return_value=DRY):
            self.assertNotIn("T rain", self.names(self.ann))

    def test_hidden_treasures_are_not_the_first_target_or_in_trails(self):
        from app import get_current_treasure
        from models import Treasure, User
        db.session.query(Treasure).filter(Treasure.created_by.is_(None)).delete()  # only the rain one left
        db.session.commit()
        self.hide(RAIN)
        ann = db.session.execute(db.select(User).filter_by(username="ann")).scalar_one()
        self.assertIsNone(get_current_treasure(ann))
        with patch("trail_api.get_route", side_effect=AssertionError("no route: no stops")):
            res = self.ann.post("/api/trail", json={"lat": 24.7905, "lon": 120.9905, "minutes": 30})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["stops"], [])
        from routing import straight_line_route
        with patch("condition_api.weather_for", return_value=RAINY), \
                patch("trail_api.get_route", side_effect=lambda pts, **kw: straight_line_route(pts)):
            res = self.ann.post("/api/trail", json={"lat": 24.7905, "lon": 120.9905, "minutes": 30})
        self.assertEqual([s["name"] for s in res.get_json()["stops"]], ["T rain"])


if __name__ == "__main__":
    unittest.main()

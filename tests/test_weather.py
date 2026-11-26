"""B: weather-aware route choices (C's #5). Tests never call Open-Meteo or OpenRouteService."""

import os
import unittest
from unittest.mock import MagicMock, patch

import requests

import weather_api
from app import create_app
from weather import (A_BIT_GREEN, GREEN, SHORTEST, WEATHER_ICONS, WeatherError, area_key, fetch_weather,
                     parse_weather, route_choice, weather_icon)

NTHU = (24.795324, 120.994796)
NEARBY = (24.7960, 120.9950)


def answer(temp=24, feels=24, rain=0.0, code=1, wind=10, uv=3, is_day=1, chance=10):
    """What Open-Meteo sends back (only the parts we read)."""
    return {"current": {"temperature_2m": temp, "apparent_temperature": feels, "precipitation": rain,
                        "weather_code": code, "wind_speed_10m": wind, "uv_index": uv, "is_day": is_day},
            "hourly": {"precipitation_probability": [chance]}}


def weather(**kw):
    return parse_weather(answer(**kw))


def ok_response(data):
    response = MagicMock(status_code=200)
    response.json.return_value = data
    return response


class RulesTest(unittest.TestCase):
    def test_parse(self):
        w = weather(temp=27.44, feels=30.06, rain=0.04, code=3, wind=12.6, uv=5.55, chance=40)
        self.assertEqual(w, {"temp_c": 27.4, "feels_c": 30.1, "rain_mm": 0.0, "rain_chance": 40, "code": 3,
                             "words": "cloudy", "wind_kmh": 13, "uv": 5.5, "is_day": True})

    def test_parse_odd_answers(self):
        for bad in ({}, {"current": {}}, {"current": {"weather_code": "x"}}):
            with self.assertRaises((KeyError, TypeError, ValueError)):
                parse_weather(bad)
        w = parse_weather({"current": {"temperature_2m": 20, "apparent_temperature": 20, "weather_code": 0}})
        self.assertEqual((w["rain_chance"], w["wind_kmh"]), (0, 0))

    def test_rain_takes_the_shortest_route(self):
        for w in (weather(rain=1.2), weather(code=63), weather(chance=70)):
            choice = route_choice(w)
            self.assertEqual((choice["kind"], choice["route_options"]), ("rain", SHORTEST))
        self.assertIn("Rain likely (70%)", route_choice(weather(chance=70))["headline"])

    def test_storm_comes_first(self):
        choice = route_choice(weather(code=95, rain=5, feels=35))
        self.assertEqual((choice["kind"], choice["route_options"]), ("storm", SHORTEST))
        self.assertIn("indoors", choice["tip"])

    def test_heat_takes_a_greener_route(self):
        self.assertEqual(route_choice(weather(feels=34))["route_options"], GREEN)
        self.assertEqual(route_choice(weather(uv=9))["kind"], "heat")
        self.assertEqual(route_choice(weather(uv=9, is_day=0))["kind"], "nice")  # no sun at night

    def test_cold_and_wind_keep_the_normal_route(self):
        self.assertEqual((route_choice(weather(feels=8))["kind"], route_choice(weather(feels=8))["route_options"]),
                         ("cold", {}))
        self.assertEqual(route_choice(weather(wind=50))["kind"], "wind")

    def test_nice_and_unknown(self):
        self.assertEqual(route_choice(weather())["route_options"], A_BIT_GREEN)
        self.assertEqual(route_choice(None), {"kind": "unknown", "headline": "", "tip": "", "route_options": {}})

    def test_icons_not_emoji(self):
        # A: the map draws a pixel icon; the headline is plain words
        cases = [weather(), weather(feels=8), weather(wind=50), weather(rain=2.0, code=63), weather(feels=40)]
        for w in cases:
            choice = route_choice(w)
            with self.subTest(kind=choice["kind"]):
                self.assertTrue(choice["headline"][0].isalpha())   # starts with a word, not an emoji
                self.assertIn(choice["kind"], WEATHER_ICONS)
        self.assertEqual(weather_icon("rain"), "rain")
        self.assertEqual(weather_icon("unknown"), "")

    def test_area_key(self):
        self.assertEqual(area_key(24.7953, 120.9948), (24.8, 120.99))


class FetchTest(unittest.TestCase):
    @patch("weather.requests.get")
    def test_fetch(self, get):
        get.return_value = ok_response(answer(code=61))
        self.assertEqual(fetch_weather(*NTHU)["words"], "light rain")
        self.assertEqual(get.call_args.kwargs["params"]["latitude"], 24.795)

    @patch("weather.requests.get", side_effect=requests.ConnectionError)
    def test_offline(self, _):
        with self.assertRaises(WeatherError):
            fetch_weather(*NTHU)

    @patch("weather.requests.get")
    def test_bad_answers(self, get):
        get.return_value = MagicMock(status_code=500)
        with self.assertRaises(WeatherError):
            fetch_weather(*NTHU)
        get.return_value = ok_response({"nothing": 1})
        with self.assertRaises(WeatherError):
            fetch_weather(*NTHU)


class ApiTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app("sqlite:///:memory:")
        self.client = self.app.test_client()
        weather_api._cache.clear()
        weather_api._down_until = 0.0
        # Never the real route service either
        env = patch.dict(os.environ, {}, clear=False)
        env.start()
        os.environ.pop("ORS_API_KEY", None)
        self.addCleanup(env.stop)

    def test_off_in_tests_by_default(self):
        with patch("weather.requests.get") as get:
            data = self.client.get(f"/api/weather?lat={NTHU[0]}&lon={NTHU[1]}").get_json()
        self.assertFalse(data["available"])
        get.assert_not_called()
        self.assertNotIn("weather", self.client.get(
            f"/api/route?points={NTHU[0]},{NTHU[1]};{NEARBY[0]},{NEARBY[1]}").get_json())

    def test_bad_position(self):
        self.assertEqual(self.client.get("/api/weather?lat=abc&lon=1").status_code, 400)

    @patch("weather.requests.get")
    def test_weather_is_cached(self, get):
        self.app.config["WEATHER"] = True
        get.return_value = ok_response(answer(feels=35))
        for _ in range(3):
            data = self.client.get(f"/api/weather?lat={NTHU[0]}&lon={NTHU[1]}").get_json()
        self.assertEqual((data["available"], data["choice"]["kind"]), (True, "heat"))
        self.assertNotIn("route_options", data["choice"])
        self.assertEqual(get.call_count, 1)

    @patch("weather.requests.get", side_effect=requests.ConnectionError)
    def test_waits_after_a_failure(self, get):
        self.app.config["WEATHER"] = True
        for _ in range(3):
            self.assertFalse(self.client.get(f"/api/weather?lat={NTHU[0]}&lon={NTHU[1]}").get_json()["available"])
        self.assertEqual(get.call_count, 1)

    @patch("routing.requests.post")
    @patch("weather.requests.get")
    def test_rain_asks_for_the_shortest_route(self, get, post):
        self.app.config["WEATHER"] = True
        get.return_value = ok_response(answer(rain=2.0, code=63))
        post.return_value = ok_response({"features": [{
            "properties": {"summary": {"distance": 120.0, "duration": 90.0}},
            "geometry": {"coordinates": [[NTHU[1], NTHU[0]], [NEARBY[1], NEARBY[0]]]}}]})
        with patch.dict(os.environ, {"ORS_API_KEY": "test-key"}):
            data = self.client.get(f"/api/route?points={NTHU[0]},{NTHU[1]};{NEARBY[0]},{NEARBY[1]}").get_json()
        self.assertEqual(post.call_args.kwargs["json"]["preference"], "shortest")
        self.assertEqual(data["weather"]["kind"], "rain")
        self.assertEqual(data["weather"]["icon"], "rain")
        self.assertEqual(data["source"], "openrouteservice")

    @patch("routing.requests.post")
    @patch("weather.requests.get")
    def test_refused_weather_settings_still_give_a_real_route(self, get, post):
        self.app.config["WEATHER"] = True
        get.return_value = ok_response(answer(feels=36))
        refused = MagicMock(status_code=400, text="green not supported")
        refused.json.return_value = {"error": {"message": "green not supported"}}
        fine = ok_response({"features": [{
            "properties": {"summary": {"distance": 150.0, "duration": 110.0}},
            "geometry": {"coordinates": [[NTHU[1], NTHU[0]], [NEARBY[1], NEARBY[0]]]}}]})
        post.side_effect = [refused, fine]
        with patch.dict(os.environ, {"ORS_API_KEY": "test-key"}):
            data = self.client.get(f"/api/route?points={NTHU[0]},{NTHU[1]};{NEARBY[0]},{NEARBY[1]}").get_json()
        self.assertEqual(data["source"], "openrouteservice")
        self.assertIn("options", post.call_args_list[0].kwargs["json"])
        self.assertNotIn("options", post.call_args_list[1].kwargs["json"])

    @patch("routing.requests.post", side_effect=requests.ConnectionError)
    @patch("weather.requests.get", side_effect=requests.ConnectionError)
    def test_no_internet_still_works(self, get, post):
        self.app.config["WEATHER"] = True
        data = self.client.get(f"/api/route?points={NTHU[0]},{NTHU[1]};{NEARBY[0]},{NEARBY[1]}").get_json()
        self.assertEqual(data["source"], "straight-line")
        self.assertNotIn("weather", data)

    def test_the_map_shows_the_weather(self):
        self.client.post("/api/register", json={"username": "ann", "password": "secret1"})
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn('id="weatherInfo"', html)
        self.assertIn("showWeather(data.weather)", html)


if __name__ == "__main__":
    unittest.main()

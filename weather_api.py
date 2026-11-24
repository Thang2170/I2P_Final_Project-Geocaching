"""Weather for the map and for route choices (owner: B). Rules live in weather.py.

- GET /api/weather?lat=..&lon=..   the weather here and how StepQuest picks your route
Routes ask weather_for() too (route_api.py), so in the rain you get the shortest route.

Open-Meteo is free and shared: answers are kept for 10 minutes per ~1 km square, and after a
failure we wait 5 minutes before asking again. Tests never call it: in-memory test apps have
WEATHER switched off (app.py), and weather tests patch weather.requests.get.
"""

import time

from flask import Blueprint, current_app, jsonify, request

from routing import check_point
from weather import WeatherError, area_key, fetch_weather, route_choice

weather_api = Blueprint("weather_api", __name__)

CACHE_S = 10 * 60
CACHE_SIZE = 100
PAUSE_S = 5 * 60
_cache = {}            # area -> (time, weather)
_down_until = 0.0


def weather_on():
    return bool(current_app.config.get("WEATHER", False))


def weather_for(lat, lon):
    """(weather dict or None, route choice). Never raises: no weather just means the normal route."""
    global _down_until
    if not weather_on():
        return None, route_choice(None)
    key = area_key(lat, lon)
    now = time.time()
    hit = _cache.get(key)
    if hit and now - hit[0] < CACHE_S:
        return hit[1], route_choice(hit[1])
    if now < _down_until:
        return None, route_choice(None)
    try:
        w = fetch_weather(lat, lon)
    except WeatherError:
        _down_until = now + PAUSE_S
        return None, route_choice(None)
    if len(_cache) >= CACHE_SIZE:
        _cache.pop(next(iter(_cache)))
    _cache[key] = (now, w)
    return w, route_choice(w)


def public_choice(choice):
    """What the map shows (not the route-service settings)."""
    return {k: choice[k] for k in ("kind", "headline", "tip")}


@weather_api.route("/api/weather")
def api_weather():
    try:
        lat, lon = check_point((request.args.get("lat"), request.args.get("lon")))
    except ValueError as err:
        return jsonify(error=str(err)), 400
    w, choice = weather_for(lat, lon)
    return jsonify(available=w is not None, weather=w, choice=public_choice(choice))

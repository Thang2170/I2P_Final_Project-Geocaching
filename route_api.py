"""The /api/route and /api/random-route endpoints (owner: A).

They live in their own Blueprint so A does not have to edit much of B's app.py.
app.py only needs two lines:

    from route_api import route_api
    app.register_blueprint(route_api)
"""

import time

from flask import Blueprint, jsonify, request

from routing import check_point, drop_reached_via, get_random_route, get_route, parse_points
from weather_api import public_choice, weather_for

route_api = Blueprint("route_api", __name__)


@route_api.route("/api/route")
def api_route():
    """GET /api/route?points=lat,lon;lat,lon[;lat,lon...]  (2 to 10 points).

    The first point is where the walker is. A middle stop they already reached
    is dropped, and "via_reached" tells the map to stop sending it.
    """
    try:
        points = parse_points(request.args.get("points", ""))
    except ValueError as err:
        return jsonify(error=str(err)), 400
    kept = drop_reached_via(points)
    # B: weather-aware: shortest in the rain, greener in the heat (weather.py)
    weather, choice = weather_for(*kept[0])
    route = get_route(kept, extra=choice["route_options"])
    if weather:
        route["weather"] = public_choice(choice)
    if len(kept) < len(points):
        route["via_reached"] = True
    return jsonify(route)


@route_api.route("/api/random-route")
def api_random_route():
    """GET /api/random-route?points=lat,lon;lat,lon[&current=lat,lon]

    points: exactly 2, you then the treasure. current (optional): the "via" of the
    route the map shows now, so the new route is a different one.
    The answer is a normal route plus "via": [lat, lon].
    """
    try:
        points = parse_points(request.args.get("points", ""))
        if len(points) != 2:
            raise ValueError("Need exactly 2 points: where you are, then the treasure")
        current = request.args.get("current")
        current_via = check_point(current.split(",")) if current else None
        route = get_random_route(points[0], points[1], current_via=current_via)
    except ValueError as err:
        return jsonify(error=str(err)), 400
    return jsonify(route)


# ------------------------------------------------------------ street crossings (Feature 7)

from crossings import (CrossingError, bounding_box, check_path, crossings_on_route,  # noqa: E402
                       fetch_crossings, parse_crossings, warning_for)
from crossing_marks import all_manual  # noqa: E402
from live_positions import parse_position  # noqa: E402

# Overpass is a free, shared service: remember answers for the same area instead of asking
# again on every reroute. Small on purpose (a dict that forgets the oldest area).
_crossing_cache = {}
CACHE_SIZE = 50


OVERPASS_PAUSE_S = 300   # after every Overpass server failed, don't make players wait again for 5 min
_overpass_down_until = 0.0


def _crossings_near(path):
    global _overpass_down_until
    key = tuple(round(x, 3) for x in bounding_box(path))  # about 100 m steps
    if key not in _crossing_cache and time.time() < _overpass_down_until:
        raise CrossingError("OpenStreetMap was unreachable a moment ago")
    if key not in _crossing_cache:
        try:
            found = fetch_crossings(path)
        except CrossingError:
            _overpass_down_until = time.time() + OVERPASS_PAUSE_S
            raise
        if len(_crossing_cache) >= CACHE_SIZE:
            _crossing_cache.pop(next(iter(_crossing_cache)))
        _crossing_cache[key] = found
    return _crossing_cache[key]


@route_api.route("/api/crossings", methods=["POST"])
def api_crossings():
    """POST {"path": [[lat, lon], ...]} (the route's path) -> the crossings you will walk over.

    If OpenStreetMap can't be reached the answer is still 200, with an empty list and a
    warning, so the map keeps working without crossing warnings.
    """
    data = request.get_json(silent=True)
    try:
        path = check_path(data.get("path") if isinstance(data, dict) else None)
    except ValueError as err:
        return jsonify(error=str(err)), 400
    # Crossings an admin added by hand come first: they work even when OpenStreetMap is down
    manual = crossings_on_route(path, all_manual())
    try:
        found = crossings_on_route(path, _crossings_near(path))
    except CrossingError as err:
        if manual:
            return jsonify(crossings=manual, source="stepquest",
                           warning=f"Only crossings added by StepQuest right now ({err}).")
        return jsonify(crossings=[], source="unavailable", warning=f"No crossing warnings right now: {err}")
    return jsonify(crossings=manual + found, source="openstreetmap")


@route_api.route("/api/crossings/warning", methods=["POST"])
def api_crossing_warning():
    """POST {"lat", "lon", "crossings": [...]} -> {"warning": {...} or null}. Python decides when to warn."""
    data = request.get_json(silent=True)
    try:
        lat, lon = parse_position(data)
        crossings = parse_crossings(data.get("crossings"))
    except (ValueError, AttributeError) as err:
        return jsonify(error=str(err)), 400
    return jsonify(warning=warning_for(lat, lon, crossings))

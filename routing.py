"""Route making for StepQuest (owner: A).

Everything here is plain Python with no Flask, so it is easy to test.
Points are (lat, lon) tuples. OpenRouteService wants [lon, lat], so the swap
happens in ONE place (get_walking_route) and nowhere else.
"""

import math
import os

import requests

from location import haversine_m

ORS_URL = "https://api.openrouteservice.org/v2/directions/foot-walking/geojson"
ORS_TIMEOUT_S = 10
WALKING_SPEED_MPS = 1.4  # about 5 km/h
MAX_POINTS = 10


class RoutingError(Exception):
    """The routing service could not give us a route."""


# ---------------------------------------------------------------- checking input


def check_point(point):
    """Return (lat, lon) as floats, or raise ValueError with a clear message."""
    try:
        lat, lon = point
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError):
        raise ValueError(f"Bad point {point!r}: need two numbers, lat and lon") from None
    if not (math.isfinite(lat) and math.isfinite(lon)):
        raise ValueError(f"Bad point {point!r}: numbers must be finite")
    if not -90 <= lat <= 90:
        raise ValueError(f"Latitude {lat} is outside -90..90")
    if not -180 <= lon <= 180:
        raise ValueError(f"Longitude {lon} is outside -180..180")
    return lat, lon


def check_points(points):
    """Check every point and the number of points. Return a list of (lat, lon)."""
    pts = [check_point(p) for p in points]
    if len(pts) < 2:
        raise ValueError("Need at least 2 points to make a route")
    if len(pts) > MAX_POINTS:
        raise ValueError(f"At most {MAX_POINTS} points are allowed")
    return pts


def parse_points(text):
    """Turn "lat,lon;lat,lon" (from a URL) into [(lat, lon), ...]."""
    parts = [p for p in (text or "").split(";") if p.strip()]
    pieces_per_part = []
    for part in parts:
        pieces = part.split(",")
        if len(pieces) != 2:
            raise ValueError(f"Bad point {part.strip()!r}: use lat,lon")
        pieces_per_part.append(pieces)
    return check_points(pieces_per_part)


# ------------------------------------------------------------------ the routes


def straight_line_route(points):
    """Offline route: straight lines between the points. Always works."""
    pts = check_points(points)
    distance_m = sum(
        haversine_m(a[0], a[1], b[0], b[1]) for a, b in zip(pts, pts[1:])
    )
    return {
        "distance_m": round(distance_m, 1),
        "duration_s": round(distance_m / WALKING_SPEED_MPS),
        "path": [[lat, lon] for lat, lon in pts],  # Leaflet wants [lat, lon]
        "source": "straight-line",
    }


def _error_message(response):
    """Pull a readable message out of an error response from the service."""
    try:
        error = response.json()["error"]
        return error["message"] if isinstance(error, dict) else str(error)
    except (KeyError, TypeError, ValueError):
        return (response.text or "")[:200] or "no details"


def get_walking_route(points, api_key=None):
    """Real walking route from OpenRouteService. Raises RoutingError on any problem."""
    pts = check_points(points)
    key = api_key or os.environ.get("ORS_API_KEY")
    if not key:
        raise RoutingError("No ORS_API_KEY set")

    body = {"coordinates": [[lon, lat] for lat, lon in pts]}  # ORS wants [lon, lat]
    headers = {
        "Authorization": key,
        "Content-Type": "application/json; charset=utf-8",
        "Accept": "application/geo+json, application/json",
    }
    try:
        response = requests.post(
            ORS_URL, json=body, headers=headers, timeout=ORS_TIMEOUT_S
        )
    except requests.RequestException as err:
        raise RoutingError(
            f"Could not reach OpenRouteService ({err.__class__.__name__})"
        ) from err

    if response.status_code != 200:
        raise RoutingError(
            f"OpenRouteService error {response.status_code}: {_error_message(response)}"
        )

    try:
        feature = response.json()["features"][0]
        summary = feature["properties"]["summary"]
        coords = feature["geometry"]["coordinates"]
        return {
            "distance_m": round(summary["distance"], 1),
            "duration_s": round(summary["duration"]),
            "path": [[c[1], c[0]] for c in coords],  # back to [lat, lon]
            "source": "openrouteservice",
        }
    except (KeyError, IndexError, TypeError, ValueError) as err:
        raise RoutingError("OpenRouteService sent an unexpected response") from err


def get_route(points):
    """Best route we can get: real walking route, else straight lines.

    Bad input raises ValueError (the caller made a mistake). A service problem
    does not: we fall back to straight lines and say why in "warning", so the
    demo still works if the internet or the free API fails.
    """
    pts = check_points(points)
    try:
        return get_walking_route(pts)
    except RoutingError as err:
        route = straight_line_route(pts)
        route["warning"] = f"Using straight lines instead of real paths: {err}"
        return route
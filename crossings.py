"""Street-crossing warnings (Feature 7, owner: A).

People walking with their eyes on a phone don't see the road. This file finds the
pedestrian crossings along your walking route (from OpenStreetMap, through the free
Overpass API) and decides when to warn you: within WARN_M of a crossing.

Plain Python plus `requests`, no Flask, so it is easy to test. If Overpass is down or
slow, the route still works: you just get no crossing warnings, and the map says so.
"""

import math

import requests

from location import haversine_m

# Overpass is free and shared, so it is sometimes busy (HTTP 429/502/504). We try the main
# server first, then public mirrors that serve the same OpenStreetMap data.
OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]
OVERPASS_TIMEOUT_S = 10  # per server: a busy one shouldn't keep the map waiting long
ON_ROUTE_M = 15      # a crossing this close to the route line is one you will walk over
WARN_M = 20          # warn when you are this close to a crossing
MARGIN_DEG = 0.0003  # about 30 m around the route, so crossings at the edges are found
MAX_PATH_POINTS = 2000
# Overpass refuses requests that don't say which app they come from (HTTP 406)
HEADERS = {"User-Agent": "StepQuest/1.0 (student geocaching project)", "Accept": "application/json"}

# OpenStreetMap's "crossing" tag says what kind of crossing it is
KIND_NAMES = {
    "traffic_signals": "crossing with traffic lights",
    "marked": "zebra crossing",
    "zebra": "zebra crossing",
    "uncontrolled": "crossing without lights",
    "unmarked": "unmarked crossing",
}


class CrossingError(Exception):
    """Overpass could not tell us where the crossings are."""


def check_path(path):
    """A route path as [[lat, lon], ...]: at least 2 points, real numbers. Raises ValueError."""
    if not isinstance(path, list) or len(path) < 2:
        raise ValueError("path must be a list of at least 2 [lat, lon] points")
    if len(path) > MAX_PATH_POINTS:
        raise ValueError(f"path has more than {MAX_PATH_POINTS} points")
    clean = []
    for point in path:
        try:
            lat, lon = float(point[0]), float(point[1])
        except (TypeError, ValueError, IndexError):
            raise ValueError("every point must be [lat, lon]") from None
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError("a point is outside the map")
        clean.append((lat, lon))
    return clean


def bounding_box(path):
    """(south, west, north, east) around the path, with a small margin."""
    lats = [p[0] for p in path]
    lons = [p[1] for p in path]
    return (min(lats) - MARGIN_DEG, min(lons) - MARGIN_DEG, max(lats) + MARGIN_DEG, max(lons) + MARGIN_DEG)


def overpass_query(box):
    """The question we ask Overpass: every crossing point inside the box, as JSON."""
    south, west, north, east = box
    area = f"{south:.6f},{west:.6f},{north:.6f},{east:.6f}"
    return (f'[out:json][timeout:{OVERPASS_TIMEOUT_S}];'
            f'(node["highway"="crossing"]({area});node["railway"="crossing"]({area}););out;')


def kind_of(tags):
    """A readable kind for the warning, from the OpenStreetMap tags."""
    if tags.get("railway") == "crossing":
        return "railway crossing"
    return KIND_NAMES.get(tags.get("crossing"), "street crossing")


def fetch_crossings(path):
    """Every crossing near the path, as [{"id", "lat", "lon", "kind"}]. Raises CrossingError."""
    query = overpass_query(bounding_box(path))
    problem = "no Overpass server answered"
    for url in OVERPASS_URLS:  # first one that answers wins
        try:
            response = requests.post(url, data={"data": query}, headers=HEADERS,
                                     timeout=OVERPASS_TIMEOUT_S + 5)
        except requests.RequestException as err:
            problem = f"Could not reach OpenStreetMap ({err.__class__.__name__})"
            continue
        if response.status_code == 200:
            return _read_answer(response)
        problem = f"OpenStreetMap error {response.status_code}"
    raise CrossingError(problem)


def _read_answer(response):
    """The crossing points from an Overpass JSON answer. Raises CrossingError."""
    try:
        elements = response.json()["elements"]
        return [{"id": e["id"], "lat": e["lat"], "lon": e["lon"], "kind": kind_of(e.get("tags", {}))}
                for e in elements if e.get("type") == "node"]
    except (KeyError, TypeError, ValueError) as err:
        raise CrossingError("OpenStreetMap sent an unexpected answer") from err


def distance_to_segment_m(point, a, b):
    """How far a point is from the line between a and b, in metres.

    For a few hundred metres the Earth is flat enough: turn degrees into metres around
    `a`, then use the usual "closest point on a line segment" maths.
    """
    to_m_lat = 111_320
    to_m_lon = 111_320 * math.cos(math.radians(a[0]))
    px, py = (point[1] - a[1]) * to_m_lon, (point[0] - a[0]) * to_m_lat
    bx, by = (b[1] - a[1]) * to_m_lon, (b[0] - a[0]) * to_m_lat
    length_sq = bx * bx + by * by
    if length_sq == 0:
        return math.hypot(px, py)
    t = max(0.0, min(1.0, (px * bx + py * by) / length_sq))  # 0 = at a, 1 = at b
    return math.hypot(px - t * bx, py - t * by)


def distance_to_path_m(point, path):
    return min(distance_to_segment_m(point, a, b) for a, b in zip(path, path[1:]))


def crossings_on_route(path, crossings, within_m=ON_ROUTE_M):
    """Only the crossings you will actually walk over (close to the route line)."""
    return [c for c in crossings if distance_to_path_m((c["lat"], c["lon"]), path) <= within_m]


def warning_for(lat, lon, crossings, warn_m=WARN_M):
    """The nearest crossing within warn_m of you, as a warning dict, or None."""
    best = None
    for c in crossings:
        d = haversine_m(lat, lon, c["lat"], c["lon"])
        if d <= warn_m and (best is None or d < best[0]):
            best = (d, c)
    if best is None:
        return None
    d, c = best
    return {"id": c["id"], "distance_m": round(d), "kind": c["kind"],
            "text": f"{c['kind'].capitalize()} in {round(d)} m: look up from your phone!"}


def parse_crossings(data):
    """The crossing list the map sends back with a position. Raises ValueError."""
    if not isinstance(data, list):
        raise ValueError("crossings must be a list")
    clean = []
    for c in data:
        try:
            clean.append({"id": int(c["id"]), "lat": float(c["lat"]), "lon": float(c["lon"]),
                          "kind": str(c.get("kind", "street crossing"))[:40]})
        except (KeyError, TypeError, ValueError):
            raise ValueError("every crossing needs id, lat and lon") from None
    return clean

"""Route making for StepQuest (owner: A).

Everything here is plain Python with no Flask, so it is easy to test.
Points are (lat, lon) tuples. OpenRouteService wants [lon, lat], so the swap
happens in ONE place (get_walking_route) and nowhere else.
"""

import math
import os
import random

import requests

from location import haversine_m

# B: api.openrouteservice.org was shut down in Nov 2026. Same paths, same keys, new host.
ORS_URL = "https://api.heigit.org/openrouteservice/v2/directions/foot-walking/geojson"
ORS_TIMEOUT_S = 10
WALKING_SPEED_MPS = 1.4  # about 5 km/h
MAX_POINTS = 10

# Random routes (Feature 6). First choice: OpenRouteService's own alternative routes,
# which are real, sensible paths. Only if it has just one, a "side-step" point is used.
ALTERNATIVES = 3            # ask for up to 3 different routes
ALT_WEIGHT_FACTOR = 1.6     # an alternative may be at most 1.6x as long as the best route
ALT_SHARE_FACTOR = 0.6      # ...and share at most 60% of its path with the others
SAME_ROUTE_M = 20           # two routes whose middles are this close count as the same route

METERS_PER_DEGREE_LAT = 111_320  # one degree of latitude is about 111 km everywhere
MIN_TRIP_M = 10        # closer than this, you are already at the treasure
MIN_DETOUR_M = 30      # less than this and the walking path usually doesn't change
MAX_DETOUR_M = 200     # more than this the side-step can land on a far-away road
MAX_DETOUR_RATIO = 1.8 # a side-step route longer than 1.8x the normal walk is refused
DETOUR_TRIES = 3       # how many side-step points to try before taking the shortest
VIA_REACHED_M = 20     # same as finding a treasure: within 20 m counts as "you got there"


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


def _ask_service(points, api_key=None, extra=None):
    """Send points to OpenRouteService and return EVERY route it sends back.

    extra: more settings for the request body (used for alternative routes).
    Raises RoutingError on any problem. The [lat, lon] <-> [lon, lat] swap is only here.
    """
    pts = check_points(points)
    key = api_key or os.environ.get("ORS_API_KEY")
    if not key:
        raise RoutingError("No ORS_API_KEY set")

    body = {"coordinates": [[lon, lat] for lat, lon in pts]}  # ORS wants [lon, lat]
    body.update(extra or {})
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
        routes = []
        for feature in response.json()["features"]:
            summary = feature["properties"]["summary"]
            coords = feature["geometry"]["coordinates"]
            routes.append({
                "distance_m": round(summary["distance"], 1),
                "duration_s": round(summary["duration"]),
                "path": [[c[1], c[0]] for c in coords],  # back to [lat, lon]
                "source": "openrouteservice",
            })
    except (KeyError, IndexError, TypeError, ValueError) as err:
        raise RoutingError("OpenRouteService sent an unexpected response") from err
    if not routes:
        raise RoutingError("OpenRouteService sent an unexpected response")
    return routes


def get_walking_route(points, api_key=None):
    """Real walking route from OpenRouteService. Raises RoutingError on any problem."""
    return _ask_service(points, api_key)[0]


def get_alternative_routes(start, end, api_key=None):
    """Up to ALTERNATIVES really different walking routes between two points.

    OpenRouteService finds them itself: each one is a sensible path (no going out
    and back), at most ALT_WEIGHT_FACTOR times longer than the best one, sharing at
    most ALT_SHARE_FACTOR of its path with the others. Raises RoutingError.
    """
    extra = {"alternative_routes": {"target_count": ALTERNATIVES,
                                    "weight_factor": ALT_WEIGHT_FACTOR,
                                    "share_factor": ALT_SHARE_FACTOR}}
    return _ask_service([start, end], api_key, extra)


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


# --------------------------------------------------------- random routes (Feature 6)


def random_via_point(start, end, rng=random):
    """Pick a random side-step point next to the straight line from start to end.

    The route then goes start -> point -> end, so each new point gives a different
    walking path to the SAME treasure. rng is the random generator: tests pass
    random.Random(seed) so they always get the same numbers.
    """
    lat1, lon1 = check_point(start)
    lat2, lon2 = check_point(end)
    trip_m = haversine_m(lat1, lon1, lat2, lon2)
    if trip_m < MIN_TRIP_M:
        raise ValueError("You are already at the treasure")

    # Work in metres on a flat map. For a walk of a few hundred metres the Earth's
    # curve doesn't matter. A degree of longitude gets shorter away from the equator.
    meters_per_degree_lon = METERS_PER_DEGREE_LAT * math.cos(math.radians(lat1))
    north_m = (lat2 - lat1) * METERS_PER_DEGREE_LAT
    east_m = (lon2 - lon1) * meters_per_degree_lon
    length_m = math.hypot(north_m, east_m)

    # One metre at a right angle to the line: turn the direction by 90 degrees.
    side_north = -east_m / length_m
    side_east = north_m / length_m

    along = rng.uniform(0.3, 0.7)  # somewhere in the middle part of the trip, not at the ends
    # Small on purpose: a point far off the line can land on a far-away road,
    # and the walk then goes out there and comes back the same way.
    sideways_m = rng.uniform(0.15, 0.35) * trip_m
    sideways_m = min(max(sideways_m, MIN_DETOUR_M), MAX_DETOUR_M)
    sideways_m *= rng.choice([-1, 1])  # left or right of the line

    via_north = along * north_m + sideways_m * side_north
    via_east = along * east_m + sideways_m * side_east
    return (
        round(lat1 + via_north / METERS_PER_DEGREE_LAT, 6),
        round(lon1 + via_east / meters_per_degree_lon, 6),
    )


def middle_point(path):
    """The point halfway along a path (by walked distance), as [lat, lon].

    It lies ON the route, so "start -> this point -> end" gives back the same route
    when the map asks again after you move (and never a detour to nowhere).
    """
    if len(path) < 3:  # no point between start and end
        return [round(path[-1][0], 6), round(path[-1][1], 6)]
    # How far you have walked when you reach each point of the path
    walked = [0.0]
    for a, b in zip(path, path[1:]):
        walked.append(walked[-1] + haversine_m(a[0], a[1], b[0], b[1]))
    half = walked[-1] / 2
    # The point in between (never the start or the treasure) closest to halfway
    best = min(range(1, len(path) - 1), key=lambda i: abs(walked[i] - half))
    return [round(path[best][0], 6), round(path[best][1], 6)]


def _is_same_route(route, current_via):
    """True if this route is the one the map is showing now (its middle is near the old via)."""
    if current_via is None:
        return False
    mid = middle_point(route["path"])
    return haversine_m(mid[0], mid[1], current_via[0], current_via[1]) <= SAME_ROUTE_M


def _side_step_route(start, end, rng, normal_m):
    """Fallback: try a few random side-step points, keep the first sensible one.

    "Sensible" = at most MAX_DETOUR_RATIO times the normal walk. If none is,
    the shortest one we tried is used, so you still get a different route.
    """
    tried = []
    for _ in range(DETOUR_TRIES):
        via = random_via_point(start, end, rng)
        route = get_route([start, via, end])
        route["via"] = list(via)
        if route["distance_m"] <= MAX_DETOUR_RATIO * normal_m:
            return route
        tried.append(route)
    return min(tried, key=lambda r: r["distance_m"])


def get_random_route(start, end, rng=random, current_via=None):
    """A different walking route to the same place.

    1. Ask OpenRouteService for alternative routes. If it has 2 or more, pick one
       at random that is not the route shown now (current_via = its middle point).
    2. Otherwise (one route only, no key, no internet): a random side-step point,
       kept small and checked so the walk can't double back (_side_step_route).
    The answer is a normal route plus "via": a point the map sends back when it
    asks for a new route after you move, so it keeps following the same path.
    """
    start, end = check_point(start), check_point(end)
    if haversine_m(start[0], start[1], end[0], end[1]) < MIN_TRIP_M:
        raise ValueError("You are already at the treasure")
    try:
        routes = get_alternative_routes(start, end)
    except RoutingError:
        routes = []

    if len(routes) >= 2:
        choices = [r for r in routes if not _is_same_route(r, current_via)] or routes
        route = rng.choice(choices)
        route["via"] = middle_point(route["path"])
        return route

    # How long the normal walk is, to judge a side-step: the service's route, else a straight line
    normal_m = routes[0]["distance_m"] if routes else haversine_m(start[0], start[1], end[0], end[1])
    return _side_step_route(start, end, rng, normal_m)


def drop_reached_via(points, reached_m=VIA_REACHED_M):
    """Remove the middle stops the walker has already reached.

    points[0] is where the walker is now and points[-1] is the treasure. Without
    this, after passing the side-step point the route would send you back to it.
    """
    start, end = points[0], points[-1]
    middle = [p for p in points[1:-1] if haversine_m(start[0], start[1], p[0], p[1]) > reached_m]
    return [start, *middle, end]
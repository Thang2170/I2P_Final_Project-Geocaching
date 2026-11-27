"""The wandering treasure: it walks around campus by itself, and nobody sees where it is (owner: B).

Players only see its footprints: where it was 3, 6, 12 and 24 hours ago. From those they guess
where it is heading, walk there, and try to catch it.

How it moves: its east-west and north-south offsets from HOME are each the sum of two slow
sine waves (periods of a few days). That keeps it inside a circle of RADIUS_M around HOME,
makes it move smoothly (several hundred metres a day), and needs no stored state: its place at
any moment is a sum. The wave phases come from a seed. wanderer_api.py makes the seed from the
app's SECRET_KEY, so reading this file on GitHub does not tell you where it is.

Plain Python with no Flask and no database, so it is easy to test.
"""

import math
import random

from location import haversine_m

HOME = (24.7953, 120.9950)      # NTHU, near the demo treasures. Change it to move the playground.
RADIUS_M = 350                  # it never goes further than this from HOME
EAST_PERIODS_DAYS = (1.3, 2.1)    # about 30 m an hour: the newest footprint is a few minutes' walk behind it
NORTH_PERIODS_DAYS = (1.7, 2.6)
FOOTPRINT_AGES_H = (24, 12, 6, 3)  # oldest first. None newer: walking to the last footprint is not enough
FOOTPRINT_STEP_S = 600          # footprints move on every 10 minutes, not every second
CATCH_RADIUS_M = 25
CLOSE_M = 100
WARM_M = 250
CATCH_COINS = 30                # once a day per player

CAUGHT, CLOSE, WARM, COLD = "caught", "close", "warm", "cold"
HINTS = {
    CAUGHT: "You caught the wandering treasure!",
    CLOSE: "You can hear it rustling. It is very close, under 100 m away.",
    WARM: "Fresh tracks. It is within 250 m of you.",
    COLD: "No sign of it here. Look at the footprints and guess where it went.",
}
METERS_PER_DEGREE_LAT = 111_320


def phases(seed):
    """Four wave phases (radians) from the seed: the same seed always gives the same walk."""
    pick = random.Random(seed)
    return tuple(pick.uniform(0, 2 * math.pi) for _ in range(4))


def offset_m(unix_s, seed):
    """(east, north) metres from HOME at this moment."""
    days = unix_s / 86400
    a, b, c, d = phases(seed)
    amp = RADIUS_M / math.sqrt(2) / 2  # two waves per axis; both axes at most: still inside RADIUS_M
    (p1, p2), (p3, p4) = EAST_PERIODS_DAYS, NORTH_PERIODS_DAYS
    east = amp * (math.sin(2 * math.pi * days / p1 + a) + math.sin(2 * math.pi * days / p2 + b))
    north = amp * (math.sin(2 * math.pi * days / p3 + c) + math.sin(2 * math.pi * days / p4 + d))
    return east, north


def position_at(unix_s, seed, home=HOME):
    """(lat, lon) of the wandering treasure at this moment."""
    east, north = offset_m(unix_s, seed)
    lat = home[0] + north / METERS_PER_DEGREE_LAT
    lon = home[1] + east / (METERS_PER_DEGREE_LAT * math.cos(math.radians(home[0])))
    return lat, lon


def age_label(hours):
    return "1 hour ago" if hours == 1 else ("yesterday" if hours == 24 else f"{hours} hours ago")


def footprints(now_unix, seed, home=HOME):
    """Where it was, oldest first. Never where it is now."""
    base = now_unix - now_unix % FOOTPRINT_STEP_S
    marks = []
    for hours in FOOTPRINT_AGES_H:
        lat, lon = position_at(base - hours * 3600, seed, home)
        marks.append({"hours_ago": hours, "label": age_label(hours), "lat": round(lat, 6), "lon": round(lon, 6)})
    return marks


def closeness(distance_m):
    if distance_m <= CATCH_RADIUS_M:
        return CAUGHT
    if distance_m <= CLOSE_M:
        return CLOSE
    return WARM if distance_m <= WARM_M else COLD


def try_catch(lat, lon, now_unix, seed, home=HOME):
    """(result, hint) for a player standing at lat, lon right now."""
    here = position_at(now_unix, seed, home)
    result = closeness(haversine_m(lat, lon, here[0], here[1]))
    return result, HINTS[result]


def metres_per_day(now_unix, seed, home=HOME):
    """How far it walked in the last 24 hours (sampled every hour), for the page's blurb."""
    points = [position_at(now_unix - h * 3600, seed, home) for h in range(24, -1, -1)]
    return round(sum(haversine_m(a[0], a[1], b[0], b[1]) for a, b in zip(points, points[1:])))

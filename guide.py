"""Eyes-free mode: find a treasure with the phone in your pocket (owner: B).

The page beeps faster as you get closer and buzzes a pattern for which way to turn, and now
and then it says where the treasure is. It works for blind players, and it is safer for
everyone: no staring at a screen while crossing a road.

Python decides everything here (how fast to beep, which buzz, what to say); the page only
plays it. Plain Python with no Flask and no database, so it is easy to test.
"""

import math

from location import FOUND_RADIUS_M

FAST_GAP_MS = 150      # beeps this often when you are nearly there
SLOW_GAP_MS = 2000     # ...and this often when you are FAR_M or more away
FAR_M = 300

AHEAD, SLIGHT_RIGHT, RIGHT, BEHIND, LEFT, SLIGHT_LEFT = (
    "ahead", "slightly right", "right", "behind", "left", "slightly left")
# Vibration patterns (milliseconds on, off, on, ...): short taps mean right, long ones mean left.
BUZZ = {
    AHEAD: [60],
    SLIGHT_RIGHT: [60, 120, 60],
    RIGHT: [60, 120, 60, 120, 60],
    SLIGHT_LEFT: [300],
    LEFT: [300, 150, 300],
    BEHIND: [600],
}
BUZZ_HELP = ("One short tap: straight ahead. Short taps: turn right. "
             "Long buzzes: turn left. One very long buzz: it is behind you.")
COMPASS = ("north", "north-east", "east", "south-east", "south", "south-west", "west", "north-west")


def bearing_deg(lat1, lon1, lat2, lon2):
    """The compass direction from point 1 to point 2: 0 is north, 90 is east."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dlon = math.radians(lon2 - lon1)
    x = math.sin(dlon) * math.cos(phi2)
    y = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlon)
    return math.degrees(math.atan2(x, y)) % 360


def compass_word(bearing):
    return COMPASS[round(bearing / 45) % 8]


def turn(bearing, heading):
    """Which way to turn, if you face `heading` and the treasure is at `bearing`."""
    angle = (bearing - heading + 180) % 360 - 180  # -180..180, negative = to your left
    if abs(angle) <= 20:
        return AHEAD
    if abs(angle) >= 150:
        return BEHIND
    if angle > 0:
        return SLIGHT_RIGHT if angle <= 60 else RIGHT
    return SLIGHT_LEFT if angle >= -60 else LEFT


def beep_gap_ms(distance_m):
    """Time between beeps: the closer, the faster."""
    if distance_m <= FOUND_RADIUS_M:
        return FAST_GAP_MS
    share = min(1.0, (distance_m - FOUND_RADIUS_M) / (FAR_M - FOUND_RADIUS_M))
    return round(FAST_GAP_MS + (SLOW_GAP_MS - FAST_GAP_MS) * share)


def spoken_distance(distance_m):
    if distance_m < 50:
        return f"{round(distance_m)} metres"
    if distance_m < 1000:
        return f"{round(distance_m, -1):.0f} metres"
    return f"{distance_m / 1000:.1f} kilometres"


def guide(name, distance_m, bearing, heading=None):
    """What the page plays now. heading is None when the phone has no compass."""
    if distance_m <= FOUND_RADIUS_M:
        return {"found": True, "gap_ms": FAST_GAP_MS, "buzz": [200, 100, 200, 100, 600],
                "direction": None, "distance_m": round(distance_m),
                "words": f"You are there! {name} is within {FOUND_RADIUS_M} metres. Feel around for it."}
    if heading is None:
        direction = compass_word(bearing)
        words = f"{name}: {spoken_distance(distance_m)} to the {direction}."
        buzz = BUZZ[AHEAD]
    else:
        direction = turn(bearing, heading)
        where = "straight ahead" if direction == AHEAD else ("behind you" if direction == BEHIND else f"to your {direction}")
        words = f"{name}: {spoken_distance(distance_m)}, {where}."
        buzz = BUZZ[direction]
    return {"found": False, "gap_ms": beep_gap_ms(distance_m), "buzz": buzz,
            "direction": direction, "words": words, "distance_m": round(distance_m)}

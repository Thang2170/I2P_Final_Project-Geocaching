"""Prove you walked: does the GPS trail before a find look like a real walk? (owner: B)

Plain Python with no Flask and no database, so it is easy to test.

While the map is open the phone sends its position every few seconds (/api/me/position).
walk_proof_api.py keeps the last TRAIL_WINDOW_S of those points. When you claim a treasure,
suspicious_reasons() looks at that trail and the claim:

- "teleport":  a jump of more than MIN_JUMP_M at more than MAX_SPEED_MPS. Faster than sprinting.
               Small jumps are ignored: phone GPS often wobbles by tens of metres.
- "no_walk":   the trail never shows you more than MIN_APPROACH_M from the treasure, so you
               seem to have appeared there (for example by typing its position into ?fake=).

Real GPS can jump too (indoors, between tall buildings), so by default a suspicious find is
still paid and an admin reviews it ("flag"). STEPQUEST_WALK_PROOF=block refuses it instead.
"""

from datetime import timezone

from location import haversine_m

TRAIL_WINDOW_S = 30 * 60   # keep (and look at) the last 30 minutes, then forget them
MAX_POINTS_KEPT = 300      # per player; at one point every 10 s that is more than 30 minutes
MAX_SPEED_MPS = 12.0       # about 43 km/h: faster than any sprint
MIN_JUMP_M = 100           # jumps shorter than this are GPS wobble, never a "teleport"
MIN_APPROACH_M = 30        # somewhere on your trail you were at least this far from the treasure

FLAG, BLOCK = "flag", "block"
MODES = (FLAG, BLOCK)

TELEPORT, NO_WALK = "teleport", "no_walk"
REASON_TEXT = {
    TELEPORT: "jumped across the map faster than anyone can run",
    NO_WALK: "appeared at the treasure without walking there",
}


def parse_mode(value):
    """The STEPQUEST_WALK_PROOF setting: "flag" (default) or "block"."""
    value = (value or FLAG).strip().lower()
    if value not in MODES:
        raise ValueError(f'STEPQUEST_WALK_PROOF must be "{FLAG}" or "{BLOCK}"')
    return value


def as_utc(when):
    """SQLite gives times back without a zone. We always save UTC, so say so."""
    return when.replace(tzinfo=timezone.utc) if when.tzinfo is None else when


def recent(points, now, window_s=TRAIL_WINDOW_S):
    """Only the points from the last window_s seconds, oldest first.

    points: (when, lat, lon) tuples, `when` a datetime.
    """
    now = as_utc(now)
    kept = [(as_utc(w), lat, lon) for w, lat, lon in points
            if 0 <= (now - as_utc(w)).total_seconds() <= window_s]
    return sorted(kept, key=lambda p: p[0])


def teleports(points):
    """Every jump that no runner could make: [(metres, seconds), ...]."""
    jumps = []
    for (t1, lat1, lon1), (t2, lat2, lon2) in zip(points, points[1:]):
        metres = haversine_m(lat1, lon1, lat2, lon2)
        seconds = max((t2 - t1).total_seconds(), 1.0)  # same second: count it as one
        if metres > MIN_JUMP_M and metres / seconds > MAX_SPEED_MPS:
            jumps.append((round(metres), round(seconds)))
    return jumps


def walked_there(points, treasure):
    """True if the trail ever shows you at least MIN_APPROACH_M from the treasure."""
    return any(haversine_m(lat, lon, treasure[0], treasure[1]) >= MIN_APPROACH_M
               for _, lat, lon in points)


def suspicious_reasons(trail, claim, treasure, now):
    """Why this find looks faked: a list of TELEPORT / NO_WALK (empty = it looks like a real walk).

    trail: (when, lat, lon) points the phone sent. claim: (lat, lon) the claim was made from.
    treasure: (lat, lon) of the treasure. now: when the claim was made.
    """
    points = recent(trail, now) + [(as_utc(now), claim[0], claim[1])]
    reasons = []
    if teleports(points):
        reasons.append(TELEPORT)
    if not walked_there(points, treasure):
        reasons.append(NO_WALK)
    return reasons


def describe(reasons):
    """The reasons in words, for the admin page and for a refused claim."""
    return "; ".join(REASON_TEXT[r] for r in reasons)

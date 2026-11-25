"""Treasure Trail: plan a walking LOOP for a step or time goal (owner: B).

Plain Python with no Flask and no database, so it is easy to test.

The player says "I want 3,000 steps" or "I have 20 minutes". We plan a loop that starts and
ends where they stand and visits as many unfound treasures as fit in that walk. This is the
"orienteering problem" (visit the most places within a distance budget). It is too slow to
solve exactly, so we use two classic, fast ideas:

1. Cheapest insertion: keep adding the treasure that makes the loop longest by the LEAST,
   at the best place in the loop, while the loop still fits the budget.
2. 2-opt: after each insertion, look for two legs that cross and "uncross" them by turning
   round the part in between. A loop with no crossings is usually close to the shortest.

Distances here are straight-line (haversine) times WALK_FACTOR, because real paths bend
round buildings. The real walking path is fetched afterwards (routing.get_route).
"""

from calculator import STEP_LENGTH_M
from location import haversine_m
from routing import MAX_POINTS, WALKING_SPEED_MPS

WALK_FACTOR = 1.3          # real walking paths are about 30% longer than the straight line
MAX_STOPS = MAX_POINTS - 2  # the routing service takes 10 points: you, the stops, you again
MIN_STEPS, MAX_STEPS = 500, 30_000
MIN_MINUTES, MAX_MINUTES = 5, 180


def parse_goal(data):
    """The walk the player asked for, as a distance budget in metres.

    Send {"steps": 3000} or {"minutes": 20}. Returns (budget_m, label).
    Raises ValueError with a message the player can read.
    """
    if not isinstance(data, dict):
        raise ValueError("Send your goal as JSON")
    steps, minutes = data.get("steps"), data.get("minutes")
    if (steps is None) == (minutes is None):
        raise ValueError("Choose steps or minutes (one of them)")
    if steps is not None:
        value = _whole_number(steps, "steps", MIN_STEPS, MAX_STEPS)
        return value * STEP_LENGTH_M, f"{value:,} steps"
    value = _whole_number(minutes, "minutes", MIN_MINUTES, MAX_MINUTES)
    return value * 60 * WALKING_SPEED_MPS, f"{value} min"


def _whole_number(value, field, low, high):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value != int(value):
        raise ValueError(f"{field} must be a whole number")
    value = int(value)
    if not low <= value <= high:
        raise ValueError(f"{field} must be between {low:,} and {high:,}")
    return value


def walk_m(a, b):
    """Estimated walking distance between two (lat, lon) points."""
    return haversine_m(a[0], a[1], b[0], b[1]) * WALK_FACTOR


def loop_length(start, points):
    """Length of the loop start -> points... -> start (estimated walking metres)."""
    return path_length(start, points, loop=True)


def path_length(start, points, loop=True):
    """start -> points..., and back to start if loop (estimated walking metres)."""
    stops = [start, *points, start] if loop else [start, *points]
    return sum(walk_m(stops[i], stops[i + 1]) for i in range(len(stops) - 1))


# B: the trail's shape. A loop comes back to where you started; a one-way trail ends at the
# last treasure (the same steps reach further, so it can visit more).
SHAPES = {"loop": "loop", "oneway": "one-way trail"}


def parse_shape(value):
    if value is None:
        return "loop"  # what trails always were
    if value not in SHAPES:
        raise ValueError(f"shape must be one of: {', '.join(SHAPES)}")
    return value


# B: skip treasures other players rated badly (you can only rate treasures you found, and a
# trail goes to ones you haven't, so it is other players' stars that count).
LOW_RATING = 2.0     # an average of 2 stars or less...
MIN_RATINGS = 2      # ...from at least 2 players (one grumpy rating is not enough)


def low_rated(ratings):
    """ids whose average rating is LOW_RATING or less. ratings: {treasure_id: [stars, ...]}."""
    return {tid for tid, stars in ratings.items()
            if len(stars) >= MIN_RATINGS and sum(stars) / len(stars) <= LOW_RATING}


def two_opt(items, length):
    """Remove crossings: try turning round every part of the loop, keep any change that is shorter.

    items: the stops in walking order (anything). length(items) -> the loop's length.
    Returns a new list in the improved order.
    """
    best = list(items)
    best_len = length(best)
    improved = True
    while improved:
        improved = False
        for i in range(len(best) - 1):
            for k in range(i + 1, len(best)):
                candidate = best[:i] + best[i:k + 1][::-1] + best[k + 1:]
                candidate_len = length(candidate)
                if candidate_len < best_len - 1e-6:
                    best, best_len, improved = candidate, candidate_len, True
    return best


def plan_trail(start, treasures, budget_m, max_stops=MAX_STOPS, loop=True):
    """Plan the trail: a loop back to start, or (loop=False) one way, ending at the last treasure.

    start: (lat, lon) of the player. treasures: dicts with "id", "lat", "lon".
    Returns {"ids": [treasure ids in walking order], "estimate_m": its length}.
    An empty "ids" means no treasure fits in this walk.
    """
    by_id = {t["id"]: (t["lat"], t["lon"]) for t in treasures}

    def length(ids):
        return path_length(start, [by_id[i] for i in ids], loop)

    # Only treasures you could reach (and, for a loop, come back from) on their own are worth trying.
    there_and_back = 2 if loop else 1
    left = sorted(i for i, p in by_id.items() if there_and_back * walk_m(start, p) <= budget_m)
    order = []  # treasure ids, in walking order
    while left and len(order) < max_stops:
        now = length(order)
        best = None  # (extra metres, treasure id, position in the loop)
        for tid in left:
            for pos in range(len(order) + 1):
                extra = length(order[:pos] + [tid] + order[pos:]) - now
                if best is None or (extra, tid) < best[:2]:
                    best = (extra, tid, pos)
        extra, tid, pos = best
        if now + extra > budget_m:
            break  # even the cheapest next treasure doesn't fit: the loop is done
        left.remove(tid)
        order = two_opt(order[:pos] + [tid] + order[pos:], length)
    return {"ids": order, "estimate_m": round(length(order), 1)}


def trail_progress(position, checkpoints, index, reach_m):
    """Which checkpoint is next, walking a trail one leg at a time (B).

    checkpoints: [(lat, lon), ...] in order, the last one is back at the start.
    index: the checkpoint you were heading to. Every checkpoint you are within reach_m of
    is ticked off, so you move on to the next one.
    Returns {"index", "meters" (to the next one, None when done), "reached" (how many
    were ticked off now), "done"}.
    """
    if not 0 <= index <= len(checkpoints):
        raise ValueError("index is outside the trail")
    start = index
    while index < len(checkpoints) and _straight_m(position, checkpoints[index]) <= reach_m:
        index += 1
    done = index >= len(checkpoints)
    meters = None if done else round(_straight_m(position, checkpoints[index]))
    return {"index": index, "meters": meters, "reached": index - start, "done": done}


def _straight_m(a, b):
    return haversine_m(a[0], a[1], b[0], b[1])


def fmt_duration(seconds):
    """1450 -> '24:10', 4000 -> '1:06:40'."""
    h, rest = divmod(int(seconds), 3600)
    m, s = divmod(rest, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def splits_text(splits):
    """The time at each checkpoint, e.g. '1 at 3:05 · 2 at 7:40 · 🏁 12:31'. splits: seconds, in order."""
    parts = [f"{n} at {fmt_duration(s)}" for n, s in enumerate(splits[:-1], start=1)]
    if splits:
        parts.append(f"🏁 {fmt_duration(splits[-1])}")
    return " · ".join(parts)


def trail_post_text(checkpoints, distance_m, duration_s, steps, calories, splits=(), shape="loop"):
    """The Community post for a finished trail, written by Python (like a run tracker)."""
    pace = duration_s / (distance_m / 1000) if distance_m >= 20 else None
    kind = "Treasure Trail" if shape == "loop" else "one-way Treasure Trail"
    text = (f"🧭 Walked a {kind}: {checkpoints} checkpoint{'s' if checkpoints != 1 else ''}, "
            f"{distance_m / 1000:.2f} km in {fmt_duration(duration_s)}")
    if pace:
        text += f" ({fmt_duration(pace)} /km)"
    text += f". {steps:,} steps, {calories:.0f} kcal."
    if splits:
        text += f" Splits: {splits_text(splits)}."
    return text


# ---------------------------------------------------------------- B: carry on a trail after a reload

TRAIL_RESUME_S = 30 * 60   # carry on if the phone reported within the last 30 minutes
MAX_CHECKPOINTS = 21       # MAX_STOPS treasures plus "back to the start", with room to spare


def _number(value, field, low, high):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a number")
    if not low <= value <= high:  # also refuses nan
        raise ValueError(f"{field} must be between {low} and {high}")
    return float(value)


def _whole(value, field, low, high):
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ValueError(f"{field} must be a whole number from {low} to {high}")
    return value


def parse_active_trail(data):
    """Check the state of a timed trail sent by the map, so it can be kept and carried on.

    Returns a clean dict: checkpoints ([{id, lat, lon, name, label}]), index, start, splits,
    meters, elapsed_s. Raises ValueError with a clear message.
    """
    if not isinstance(data, dict):
        raise ValueError("send JSON")
    raw = data.get("checkpoints")
    if not isinstance(raw, list) or not 1 <= len(raw) <= MAX_CHECKPOINTS:  # one-way to 1 treasure: 1
        raise ValueError(f"checkpoints must be a list of 1 to {MAX_CHECKPOINTS} points")
    checkpoints = []
    for cp in raw:
        if not isinstance(cp, dict):
            raise ValueError("each checkpoint must be an object")
        cid = cp.get("id")
        if cid is not None:
            cid = _whole(cid, "checkpoint id", 1, 10**9)
        name = cp.get("name")
        if not isinstance(name, str) or not 1 <= len(name) <= 100:
            raise ValueError("each checkpoint needs a name of 1 to 100 characters")
        label = str(cp.get("label", ""))[:4]
        checkpoints.append({"id": cid, "lat": _number(cp.get("lat"), "lat", -90, 90),
                            "lon": _number(cp.get("lon"), "lon", -180, 180), "name": name, "label": label})
    start = data.get("start")
    if not isinstance(start, list) or len(start) != 2:
        raise ValueError("start must be [lat, lon]")
    start = [_number(start[0], "lat", -90, 90), _number(start[1], "lon", -180, 180)]
    elapsed_s = _whole(data.get("elapsed_s"), "elapsed_s", 0, 86_400)
    splits = data.get("splits", [])
    if not isinstance(splits, list) or len(splits) > MAX_CHECKPOINTS:
        raise ValueError("splits must be a list of times")
    splits = [_whole(s, "split", 0, elapsed_s) for s in splits]
    if splits != sorted(splits):
        raise ValueError("splits must go up")
    return {
        "checkpoints": checkpoints,
        "index": _whole(data.get("index"), "index", 0, len(checkpoints) - 1),
        "start": start,
        "splits": splits,
        "meters": _number(data.get("meters"), "meters", 0, 100_000),
        "elapsed_s": elapsed_s,
        "shape": parse_shape(data.get("shape")),
    }


def can_carry_on(since_update_s):
    """A kept trail is carried on only if the phone reported recently."""
    return 0 <= since_update_s <= TRAIL_RESUME_S


# ---------------------------------------------------------------- B: trail history and personal bests

def trail_signature(shape, treasure_ids):
    """Which trail this is, so walks of the same trail can be compared.

    The same shape through the same treasures is the same trail, in whatever order you walked
    them. None if there are no treasure ids (an older walk, before this was kept).
    """
    if not treasure_ids:
        return None
    return f"{parse_shape(shape)}:" + "-".join(str(i) for i in sorted(set(treasure_ids)))


def best_change(previous_best_s, duration_s):
    """Compare a new walk with your best time on the same trail.

    Returns {"personal_best", "first_time", "previous_best_s", "faster_by_s"}.
    The first walk of a trail is its first best; a tie is not a new best.
    """
    if previous_best_s is None:
        return {"personal_best": True, "first_time": True, "previous_best_s": None, "faster_by_s": 0}
    faster = previous_best_s - duration_s
    return {"personal_best": faster > 0, "first_time": False, "previous_best_s": previous_best_s,
            "faster_by_s": max(0, faster)}


def best_text(change):
    """The line added to the Community post, or "" if there is nothing to brag about."""
    if change["personal_best"] and not change["first_time"]:
        return f" 🏅 New personal best, {fmt_duration(change['faster_by_s'])} faster than before!"
    return ""


def pace_text(distance_m, duration_s):
    pace = duration_s / (distance_m / 1000) if distance_m >= 20 else None
    return f"{fmt_duration(pace)} /km" if pace else "–"

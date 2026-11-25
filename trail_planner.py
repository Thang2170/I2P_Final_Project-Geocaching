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
    stops = [start, *points, start]
    return sum(walk_m(stops[i], stops[i + 1]) for i in range(len(stops) - 1))


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


def plan_trail(start, treasures, budget_m, max_stops=MAX_STOPS):
    """Plan the loop.

    start: (lat, lon) of the player. treasures: dicts with "id", "lat", "lon".
    Returns {"ids": [treasure ids in walking order], "estimate_m": loop length}.
    An empty "ids" means no treasure fits in this walk.
    """
    by_id = {t["id"]: (t["lat"], t["lon"]) for t in treasures}

    def length(ids):
        return loop_length(start, [by_id[i] for i in ids])

    # Only treasures you could reach and come back from on their own are worth trying.
    left = sorted(i for i, p in by_id.items() if 2 * walk_m(start, p) <= budget_m)
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


def trail_post_text(checkpoints, distance_m, duration_s, steps, calories, splits=()):
    """The Community post for a finished trail, written by Python (like a run tracker)."""
    pace = duration_s / (distance_m / 1000) if distance_m >= 20 else None
    text = (f"🧭 Walked a Treasure Trail: {checkpoints} checkpoint{'s' if checkpoints != 1 else ''}, "
            f"{distance_m / 1000:.2f} km in {fmt_duration(duration_s)}")
    if pace:
        text += f" ({fmt_duration(pace)} /km)"
    text += f". {steps:,} steps, {calories:.0f} kcal."
    if splits:
        text += f" Splits: {splits_text(splits)}."
    return text

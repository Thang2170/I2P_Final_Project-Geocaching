"""Rules for carrying on a journey after the phone lost its connection (owner: A).

Plain Python with no Flask and no database, so it is easy to test.

When you start a journey the server remembers it, with a deadline. If your phone loses
signal, closes the page or reloads, you can carry on until the deadline. The deadline
depends on how far the treasure is: a 5-minute walk doesn't need 4 hours, and a long
walk shouldn't run out while you're still on your way.
"""

from datetime import timedelta, timezone

DETOUR = 1.4             # real paths are about 40% longer than the straight line
SLOW_WALK_MS = 1.0       # a slow walk with stops (normal walking is about 1.4 m/s)
TIME_FACTOR = 2          # allow twice the slow walking time...
EXTRA_S = 10 * 60        # ...plus 10 minutes (getting lost, waiting at lights)
MIN_WINDOW_S = 15 * 60   # never less than 15 minutes
MAX_WINDOW_S = 4 * 3600  # never more than 4 hours


def expected_walk_s(straight_m):
    """About how long a slow walk to a place this far away (straight line) takes, in seconds."""
    if straight_m < 0:
        raise ValueError("distance can't be negative")
    return straight_m * DETOUR / SLOW_WALK_MS


def resume_window_s(straight_m):
    """How long a journey can be carried on after it starts, in whole seconds."""
    window = TIME_FACTOR * expected_walk_s(straight_m) + EXTRA_S
    return int(min(max(window, MIN_WINDOW_S), MAX_WINDOW_S))


def as_utc(when):
    """SQLite gives times back without a zone. We always save UTC, so say so."""
    return when.replace(tzinfo=timezone.utc) if when.tzinfo is None else when


def deadline_for(started_at, straight_m):
    """When the journey stops being resumable."""
    return as_utc(started_at) + timedelta(seconds=resume_window_s(straight_m))


def seconds_left(deadline, now):
    """Whole seconds until the deadline (0 once it has passed)."""
    return max(0, int((as_utc(deadline) - as_utc(now)).total_seconds()))


def can_resume(deadline, now):
    return as_utc(now) <= as_utc(deadline)


def parse_progress(data):
    """{"meters": .., "elapsed_s": ..} sent while walking. Returns (meters, elapsed_s) or raises ValueError."""
    if not isinstance(data, dict):
        raise ValueError("Send JSON with meters and elapsed_s")
    try:
        meters, elapsed = float(data.get("meters")), float(data.get("elapsed_s"))
    except (TypeError, ValueError):
        raise ValueError("meters and elapsed_s must be numbers") from None
    if meters < 0 or elapsed < 0 or meters > 200_000 or elapsed > MAX_WINDOW_S * 2:
        raise ValueError("meters or elapsed_s is out of range")
    return round(meters, 1), int(elapsed)

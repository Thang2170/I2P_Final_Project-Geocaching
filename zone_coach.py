"""Heart-rate zone coach: bonus coins, too-hard warnings and the cool-down quest. Owner: B.

Plain Python with no Flask and no database. Readings are (time, heart rate) pairs from the
band, oldest first; times are datetimes. Zones come from health.py (A's), so the map and
the Health page always agree.
"""

from health import ZONE_LIMITS, ZONE_NAMES, zone_of

SECONDS_EACH = 5            # the band sends one reading every 5 s (same as energy.py)
MAX_GAP_S = 15              # readings further apart than this break a "continuous" run

# Bonus coins for steady effort: 60-80% of your max heart rate (C's idea)
BONUS_LOW, BONUS_HIGH = 0.6, 0.8
BONUS_EVERY_S = 3 * 60      # 1 coin for every 3 minutes in the bonus zone
MAX_BONUS = 10              # at most 10 coins per hunt

# Warnings when you stay in a hard zone too long
HARD, MAXIMUM = 3, 4        # zone numbers from health.zone_of
HARD_LIMIT_S = 10 * 60      # 10 minutes in Hard or above
MAXIMUM_LIMIT_S = 2 * 60    # 2 minutes in Maximum

# The cool-down quest at the end of a hunt
COOLDOWN_S = 3 * 60         # walk gently for 3 minutes...
COOLDOWN_BELOW = ZONE_LIMITS[1]  # ...below 70% of your max (the Light zone or easier)
COOLDOWN_WINDOW_S = 20 * 60  # ...within 20 minutes of finishing
COOLDOWN_REWARD = 3


def in_bonus_zone(hr, hr_max):
    return BONUS_LOW <= hr / hr_max < BONUS_HIGH


def bonus_seconds(readings, hr_max):
    """Seconds spent in the bonus zone (each reading counts SECONDS_EACH)."""
    return sum(SECONDS_EACH for _, hr in readings if in_bonus_zone(hr, hr_max))


def bonus_coins(seconds):
    return min(MAX_BONUS, int(seconds // BONUS_EVERY_S))


def zone_seconds(readings, hr_max):
    """Seconds in each of the five zones."""
    seconds = [0] * 5
    for _, hr in readings:
        seconds[zone_of(hr, hr_max)] += SECONDS_EACH
    return seconds


def run_seconds(readings, keep):
    """How long the latest readings have kept keep(hr) true without a break, in seconds.

    The run ends at the newest reading; it stops at the first reading (going back) that
    fails keep(), or at a gap longer than MAX_GAP_S.
    """
    run_start = None
    newer = None
    for when, hr in reversed(readings):
        if not keep(hr) or (newer is not None and (newer - when).total_seconds() > MAX_GAP_S):
            break
        run_start = when
        newer = when
    if run_start is None:
        return 0
    return round((readings[-1][0] - run_start).total_seconds()) + SECONDS_EACH


def warning(readings, hr_max):
    """A warning text if you have stayed too hard for too long, else None."""
    if not readings:
        return None
    in_max = run_seconds(readings, lambda hr: zone_of(hr, hr_max) >= MAXIMUM)
    if in_max >= MAXIMUM_LIMIT_S:
        return (f"You have been at your Maximum for {in_max // 60} min. "
                "Slow down to a walk and let your heart rate come down.")
    in_hard = run_seconds(readings, lambda hr: zone_of(hr, hr_max) >= HARD)
    if in_hard >= HARD_LIMIT_S:
        return (f"You have been in the Hard zone for {in_hard // 60} min. "
                "Ease off a little: the 60-80% zone earns bonus coins too.")
    return None


def cooldown_bpm(hr_max):
    """Stay under this heart rate for the cool-down."""
    return round(COOLDOWN_BELOW * hr_max)


def longest_run(readings, keep):
    """The longest stretch (seconds) where keep(hr) stayed true without a break."""
    best, start, newest_ok = 0, None, None
    for when, hr in readings:
        if not keep(hr) or (newest_ok is not None and (when - newest_ok).total_seconds() > MAX_GAP_S):
            start = None
        if keep(hr):
            start = start or when
            newest_ok = when
            best = max(best, round((when - start).total_seconds()) + SECONDS_EACH)
        else:
            newest_ok = None
    return best


def cooldown_progress(readings, hr_max):
    """Seconds of the cool-down done (0..COOLDOWN_S), from the readings after the hunt.

    The best gentle stretch counts, so a short climb later does not undo a finished cool-down.
    """
    return min(COOLDOWN_S, longest_run(readings, lambda hr: hr < COOLDOWN_BELOW * hr_max))


def now_report(readings, hr_max):
    """Everything the map shows about your heart rate during a hunt."""
    if not readings:
        return {"has_band": False, "text": "Wear your band to see your heart-rate zone."}
    hr = readings[-1][1]
    zone = zone_of(hr, hr_max)
    seconds = bonus_seconds(readings, hr_max)
    return {
        "has_band": True,
        "hr": hr,
        "percent": round(100 * hr / hr_max),
        "zone": zone,
        "zone_name": ZONE_NAMES[zone],
        "in_bonus_zone": in_bonus_zone(hr, hr_max),
        "bonus_seconds": seconds,
        "bonus_coins": bonus_coins(seconds),
        "zone_seconds": zone_seconds(readings, hr_max),
        "warning": warning(readings, hr_max),
    }

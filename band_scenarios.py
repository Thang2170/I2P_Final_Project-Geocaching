"""Pretend band readings for live demos (owner: B). Plain Python, no Flask, no network.

simulate_band.py sends these to the app, one reading every 5 seconds, so the live features
can be shown on stage without the real band: the heart-rate zone on the map, the too-hard
warnings, the cool-down quest and the safety stops. Each scenario is a function of the
seconds since it started. Heart rates follow your max heart rate (health.max_heart_rate),
so the zones come out right for any age.

A scenario may also "backfill": send the last few minutes at once (as if the band had been
on all along), so a warning that needs 10 minutes in a zone shows up straight away.
"""

import math
import random

from health import max_heart_rate

EVERY_S = 5


def _reading(hr, spo2=97.5, steps=9, temp_c=33.5):
    return {"hr": int(round(hr)), "spo2": round(spo2, 1), "steps": int(round(steps)), "temp_c": round(temp_c, 1)}


def _wobble(rng, size):
    return rng.uniform(-size, size)


# Each scenario: (what it shows, how to see it, backfill seconds, function(t, hr_max, rng) -> reading)

def _calm(t, hr_max, rng):
    return _reading(0.5 * hr_max + _wobble(rng, 3), steps=8 + _wobble(rng, 1))


def _zone(t, hr_max, rng):
    # 60-80% of max: the bonus zone (zone_coach.py)
    return _reading(0.7 * hr_max + 6 * math.sin(t / 40) + _wobble(rng, 2), steps=11 + _wobble(rng, 1))


def _hard(t, hr_max, rng):
    return _reading(0.85 * hr_max + _wobble(rng, 2), steps=13 + _wobble(rng, 1))


def _maximum(t, hr_max, rng):
    return _reading(0.95 * hr_max + _wobble(rng, 1), steps=15 + _wobble(rng, 1))


def _cooldown(t, hr_max, rng):
    # from the bonus zone down to an easy walk in the first minute, then easy (under 70%)
    start, end = 0.75 * hr_max, 0.55 * hr_max
    hr = end + (start - end) * max(0.0, 1 - t / 60)
    return _reading(hr + _wobble(rng, 2), steps=8 + _wobble(rng, 1))


def _low_spo2(t, hr_max, rng):
    # normal for 20 seconds, then blood oxygen drops to about 88%
    spo2 = 97 + _wobble(rng, 0.5) if t < 20 else 88 + _wobble(rng, 0.8)
    return _reading(0.6 * hr_max + _wobble(rng, 2), spo2=spo2)


def _high_hr(t, hr_max, rng):
    # normal for 20 seconds, then well above the max (safety.py stops after 30 s)
    hr = 0.65 * hr_max if t < 20 else hr_max + 12
    return _reading(hr + _wobble(rng, 1), steps=14)


def _low_hr(t, hr_max, rng):
    hr = 0.55 * hr_max if t < 20 else 36
    return _reading(hr + _wobble(rng, 1), steps=7)


def _rehab(t, hr_max, rng):
    # a gentle walk, under 70% of max (goals.py: rehab walking)
    return _reading(0.58 * hr_max + _wobble(rng, 2), steps=7 + _wobble(rng, 1))


SCENARIOS = {
    "calm": ("an easy walk", "Map journey panel: zone 'Very light'. Health page: a normal walk.", 0, _calm),
    "zone": ("a steady walk at 60-80% of max", "Map: zone in green and bonus minutes counting. "
             "Save a hunt for +1 coin per 3 minutes.", 9 * 60, _zone),
    "hard": ("10 minutes too hard", "Map: a red 'Hard zone for 10 min' warning in the journey panel.", 10 * 60, _hard),
    "maximum": ("2 minutes at maximum", "Map: a red 'Maximum for 2 min' warning.", 2 * 60, _maximum),
    "cooldown": ("slowing down after a hunt", "Finish and save a hunt first, then run this: the cool-down quest "
                 "fills up and pays +3 after 3 minutes.", 0, _cooldown),
    "low-spo2": ("blood oxygen dropping", "Start a journey first. After about 35 seconds the hunt stops and the "
                 "red 'Low blood oxygen' warning appears.", 0, _low_spo2),
    "high-hr": ("heart rate far too high", "Start a journey first. After about 50 seconds the hunt stops with "
                "'Heart rate too high'.", 0, _high_hr),
    "low-hr": ("heart rate far too low", "Start a journey first. After about 50 seconds the hunt stops with "
               "'Heart rate unusually low'.", 0, _low_hr),
    "rehab": ("a gentle rehab walk", "Home page: with the rehab goal, walking minutes count and no "
              "'slow down' advice.", 0, _rehab),
}


def reading_at(scenario, t, age=20, seed=None):
    """The reading t seconds into a scenario (t can be negative: before it started, for backfill)."""
    if scenario not in SCENARIOS:
        raise ValueError(f"scenario must be one of: {', '.join(SCENARIOS)}")
    rng = random.Random(f"{seed}:{t}" if seed is not None else None)
    return SCENARIOS[scenario][3](max(t, 0), max_heart_rate(age), rng)


def backfill(scenario, age=20, seed=None):
    """The readings for the scenario's backfill, oldest first, each with its age_s.

    They describe the same scenario carried on for a while, ending now.
    """
    seconds = SCENARIOS[scenario][2]
    out = []
    for age_s in range(seconds, 0, -EVERY_S):
        # the scenario's "steady" part (t past its start-up), so a backfill isn't a ramp
        out.append(reading_at(scenario, 600, age, seed if seed is None else f"{seed}:-{age_s}") | {"age_s": age_s})
    return out

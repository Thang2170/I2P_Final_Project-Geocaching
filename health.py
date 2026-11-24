"""Health rules for the StepQuest wearable (owner: A). Plain Python, no Flask, no database.

The ESP32 sends a reading every few seconds: heart rate, blood oxygen (SpO2) and steps.
This file turns one walk's readings into a summary and plain-language advice.

Every number here is an ESTIMATE from cheap sensors and well-known formulas. StepQuest is a
walking game, not a medical device, and the page says so.
"""

from datetime import timedelta, timezone

DEFAULT_AGE = 20
SESSION_GAP_S = 10 * 60         # readings more than 10 minutes apart belong to different walks
STEP_LENGTH_M = 0.75            # same as calculator.py
MAX_BATCH = 500                 # readings in one upload
MAX_AGE_S = 7 * 24 * 3600       # the device may keep readings offline for up to a week
ZONE_LIMITS = (0.6, 0.7, 0.8, 0.9)   # % of max heart rate where zones 2, 3, 4, 5 start
ZONE_NAMES = ("Very light", "Light", "Moderate", "Hard", "Maximum")
LOW_SPO2 = 92                   # below this (resting, at sea level) people usually see a doctor


# ------------------------------------------------------------ reading what the device sends


def _number(value, low, high, whole=False):
    """value as a number between low and high, None if missing, ValueError if nonsense."""
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{value!r} is not a number") from None
    if not low <= number <= high:
        raise ValueError(f"{number} is outside {low}..{high}")
    return int(round(number)) if whole else round(number, 1)


def parse_batch(data):
    """The upload {"readings": [{"age_s", "hr", "spo2", "steps", "temp_c"}, ...]} -> clean list.

    age_s = how many seconds ago the device measured it (the ESP32 has no reliable clock
    when it's offline, but it can count seconds). Raises ValueError for a bad upload.
    """
    if not isinstance(data, dict) or not isinstance(data.get("readings"), list):
        raise ValueError('Send JSON {"readings": [...]}')
    readings = data["readings"]
    if not readings or len(readings) > MAX_BATCH:
        raise ValueError(f"Send between 1 and {MAX_BATCH} readings")
    clean = []
    for r in readings:
        if not isinstance(r, dict):
            raise ValueError("Every reading must be an object")
        clean.append({
            "age_s": _number(r.get("age_s", 0), 0, MAX_AGE_S, whole=True),
            "hr": _number(r.get("hr"), 30, 230, whole=True),
            "spo2": _number(r.get("spo2"), 50, 100),
            "steps": _number(r.get("steps", 0), 0, 2000, whole=True),
            "temp_c": _number(r.get("temp_c"), 20, 45),
        })
    return clean


# ------------------------------------------------------------ the maths


def as_utc(when):
    return when.replace(tzinfo=timezone.utc) if when.tzinfo is None else when


def split_walks(readings, gap_s=SESSION_GAP_S):
    """Readings sorted by time -> a list of walks (lists), split where there's a long pause."""
    walks = []
    for r in readings:
        if walks and (as_utc(r["at"]) - as_utc(walks[-1][-1]["at"])) <= timedelta(seconds=gap_s):
            walks[-1].append(r)
        else:
            walks.append([r])
    return walks


def max_heart_rate(age):
    """Tanaka's formula (2001): 208 - 0.7 x age. Better than the old 220 - age."""
    return round(208 - 0.7 * age)


def resting_estimate(heart_rates):
    """About your resting heart rate: the average of the lowest 10 % of the walk's readings."""
    if len(heart_rates) < 5:
        return None
    lowest = sorted(heart_rates)[:max(1, len(heart_rates) // 10)]
    return round(sum(lowest) / len(lowest))


def zone_of(hr, hr_max):
    """0..4: which of the five training zones this heart rate is in."""
    share = hr / hr_max
    return sum(1 for limit in ZONE_LIMITS if share >= limit)


def zone_minutes(heart_rates, seconds_each, hr_max):
    """Minutes spent in each of the five zones."""
    minutes = [0.0] * 5
    for hr in heart_rates:
        minutes[zone_of(hr, hr_max)] += seconds_each / 60
    return [round(m, 1) for m in minutes]


def vo2max_estimate(hr_max, hr_rest):
    """Uth et al. (2004): VO2max ~ 15.3 x max HR / resting HR, in ml/kg/min. A rough guide only:
    the real number needs a lab test with a breathing mask."""
    if not hr_rest:
        return None
    return round(15.3 * hr_max / hr_rest, 1)


def calories_from_hr(avg_hr, minutes, weight_kg, age):
    """Keytel et al. (2005) heart-rate formula, the average of its male and female versions
    (we don't ask for sex). kcal, never below 0."""
    if not avg_hr or minutes <= 0:
        return None
    male = (-55.0969 + 0.6309 * avg_hr + 0.1988 * weight_kg + 0.2017 * age) / 4.184
    female = (-20.4022 + 0.4472 * avg_hr - 0.1263 * weight_kg + 0.074 * age) / 4.184
    return round(max(0.0, (male + female) / 2 * minutes))


def summarize(walk, age=DEFAULT_AGE, weight_kg=65, resting_hr=None):
    """One walk's readings -> every number the Health page shows.

    resting_hr: the player's own resting heart rate if they told us (much better than our
    guess from the walk, which is always a bit high because walking raises it)."""
    start, end = as_utc(walk[0]["at"]), as_utc(walk[-1]["at"])
    minutes = max((end - start).total_seconds() / 60, len(walk) * 5 / 60)  # at least 5 s per reading
    heart_rates = [r["hr"] for r in walk if r.get("hr")]
    oxygen = [r["spo2"] for r in walk if r.get("spo2")]
    steps = sum(r.get("steps") or 0 for r in walk)
    hr_max = max_heart_rate(age)
    seconds_each = minutes * 60 / len(walk)
    rest = resting_hr or resting_estimate(heart_rates)
    avg_hr = round(sum(heart_rates) / len(heart_rates)) if heart_rates else None
    return {
        "start": start.isoformat(),
        "minutes": round(minutes, 1),
        "steps": steps,
        "distance_m": round(steps * STEP_LENGTH_M),
        "cadence_spm": round(steps / minutes) if minutes else 0,
        "hr_avg": avg_hr,
        "hr_max": max(heart_rates) if heart_rates else None,
        "hr_min": min(heart_rates) if heart_rates else None,
        "hr_rest_estimate": rest,
        "hr_rest_source": "you" if resting_hr else "guessed from this walk",
        "hr_max_for_age": hr_max,
        "zones": [{"name": n, "minutes": m} for n, m in zip(ZONE_NAMES, zone_minutes(heart_rates, seconds_each, hr_max))],
        "spo2_avg": round(sum(oxygen) / len(oxygen), 1) if oxygen else None,
        "spo2_min": min(oxygen) if oxygen else None,
        "calories": calories_from_hr(avg_hr, minutes, weight_kg, age),
        "vo2max_estimate": vo2max_estimate(hr_max, rest),
        "age": age,
        "readings": len(walk),
    }


def heart_chart_points(walk, width=300, height=80):
    """The heart-rate line for the page, as SVG polyline points ("x,y x,y ..."). Python draws
    the chart, the page only shows it."""
    values = [r["hr"] for r in walk if r.get("hr")]
    if len(values) < 2:
        return ""
    low, high = min(values) - 5, max(values) + 5
    step = width / (len(values) - 1)
    return " ".join(f"{i * step:.1f},{height - (v - low) / (high - low) * height:.1f}" for i, v in enumerate(values))


def rules_advice(s):
    """Plain-language advice from the numbers. Used when the local AI isn't running, and
    as facts the AI must stick to when it is."""
    tips = []
    if s["steps"]:
        tips.append(f"You walked about {s['distance_m']} m ({s['steps']} steps) in {s['minutes']:.0f} minutes, "
                    f"{s['cadence_spm']} steps a minute.")
        if s["cadence_spm"] >= 100:
            tips.append("That's a brisk pace (100+ steps a minute counts as moderate exercise).")
        elif s["cadence_spm"] >= 60:
            tips.append("A relaxed pace. Try a few faster minutes next time to reach 100 steps a minute.")
    if s["hr_avg"]:
        zones = {z["name"]: z["minutes"] for z in s["zones"]}
        active = zones["Moderate"] + zones["Hard"] + zones["Maximum"]
        tips.append(f"Your heart averaged {s['hr_avg']} bpm (highest {s['hr_max']}); "
                    f"{active:.0f} minutes were moderate or harder.")
        if zones["Maximum"] > 5:
            tips.append("You spent a while at your maximum. Slow down if you feel dizzy or very short of breath.")
        if s["vo2max_estimate"]:
            tips.append(f"Estimated fitness (VO2max) is about {s['vo2max_estimate']} ml/kg/min. "
                        "It's a rough guess from your heart rate, not a lab test.")
    if s["spo2_min"] is not None:
        if s["spo2_min"] < LOW_SPO2:
            tips.append(f"Your blood oxygen dipped to {s['spo2_min']} %. Cheap sensors often misread when the "
                        "finger moves, so check the sensor fits well. If you also feel unwell, see a doctor.")
        else:
            tips.append(f"Blood oxygen stayed healthy (lowest {s['spo2_min']} %).")
    if s["calories"]:
        tips.append(f"About {s['calories']} kcal burned (estimated from heart rate).")
    if not tips:
        tips.append("Not enough readings yet. Wear the sensor for a whole walk.")
    return tips

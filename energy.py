"""Calories and steps for a walk, from the best data we have (owner: B; formulas picked with C).

Plain Python with no Flask and no database, so it is easy to test.

Three formulas, best first:
1. HEART RATE from the band (health.py's Keytel 2005 formula). Used when the band's readings
   cover at least BAND_COVERAGE of the walk. The band's step counter is used for steps too.
2. SPEED (ACSM walking and running equations). When we know how long the walk took:
     walking:  VO2 = 3.5 + 0.1 x speed            (ml of oxygen per kg per minute, speed in m/min)
     running:  VO2 = 3.5 + 0.2 x speed            (from RUN_FROM_M_PER_MIN, about 8 km/h)
     kcal = VO2 x weight(kg) / 1000 x 5 x minutes  (about 5 kcal for each litre of oxygen)
   So a brisk walk burns more than a stroll over the same distance.
3. DISTANCE only (a planned route): calculator.py's 0.5 x weight(kg) x km.

Every number is an estimate. StepQuest is a walking game, not a medical device.
"""

from calculator import calories_from_distance, steps_from_distance
from health import calories_from_hr

BAND_COVERAGE = 0.5        # band readings must cover half the walk to be trusted
SECONDS_PER_READING = 5    # the band sends a reading about every 5 seconds
RUN_FROM_M_PER_MIN = 134   # 8 km/h: from here the running equation fits better
KCAL_PER_LITRE_O2 = 5.0

HEART, SPEED, DISTANCE = "heart rate", "speed", "distance"
SOURCE_TEXT = {
    HEART: "❤ from your band's heart rate",
    SPEED: "from your speed and weight",
    DISTANCE: "from the distance and your weight",
}


def acsm_kcal(distance_m, duration_s, weight_kg):
    """Calories from the ACSM walking (or running) equation."""
    minutes = duration_s / 60
    if minutes <= 0:
        return None
    speed = distance_m / minutes  # metres a minute
    per_metre = 0.2 if speed >= RUN_FROM_M_PER_MIN else 0.1
    vo2 = 3.5 + per_metre * speed
    return vo2 * weight_kg / 1000 * KCAL_PER_LITRE_O2 * minutes


def band_covers(readings, duration_s):
    """True if the band sent enough heart-rate readings for this walk."""
    if not duration_s:
        return False
    with_hr = sum(1 for r in readings if r.get("hr"))
    return with_hr * SECONDS_PER_READING >= BAND_COVERAGE * duration_s


def walk_energy(distance_m, weight_kg, age, duration_s=None, band=(), step_length_m=None):
    """{"steps", "calories", "source", "source_text"} for a walk.

    band: the band's readings during the walk, dicts with "hr" and "steps".
    step_length_m: the player's own step length (from their height), else calculator.py's.
    """
    band = list(band)
    if band_covers(band, duration_s):
        rates = [r["hr"] for r in band if r.get("hr")]
        calories = calories_from_hr(round(sum(rates) / len(rates)), duration_s / 60, weight_kg, age) or 0
        band_steps = sum(r.get("steps") or 0 for r in band)
        steps = band_steps if band_steps else _steps(distance_m, step_length_m)
        source = HEART
    elif duration_s:
        calories = acsm_kcal(distance_m, duration_s, weight_kg) or 0
        steps, source = _steps(distance_m, step_length_m), SPEED
    else:
        calories = calories_from_distance(distance_m, weight_kg)
        steps, source = _steps(distance_m, step_length_m), DISTANCE
    return {"steps": steps, "calories": round(calories, 1), "source": source, "source_text": SOURCE_TEXT[source]}


def _steps(distance_m, step_length_m):
    if step_length_m:
        return round(distance_m / step_length_m)
    return steps_from_distance(distance_m)

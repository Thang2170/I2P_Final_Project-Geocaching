"""Rain and night treasures: some treasures only appear in the rain, or after dark (owner: B).

Plain Python with no Flask and no database, so it is easy to test.
condition_api.py saves each treasure's condition and asks these rules whether it shows now.

"After dark" is worked out from where the sun really is at that spot (the NOAA formula below),
so it follows the seasons: earlier in winter, later in summer. "Raining" comes from the weather
check the routes already use (weather.py); with no weather (offline, tests) it is not raining.
The player who hid a treasure always sees it, with a note saying when others can.
"""

import math
from datetime import timezone

from weather import RAIN_CODES, RAIN_MM

ALWAYS = "always"
RAIN = "rain"
NIGHT = "night"
CONDITIONS = (ALWAYS, RAIN, NIGHT)

DARK_BELOW_DEG = -6   # civil twilight: once the sun is 6 degrees under the horizon it is dark

LABELS = {ALWAYS: "Always", RAIN: "Only in the rain", NIGHT: "Only after dark"}


def parse_condition(value):
    """The condition from the upload form. Empty means ALWAYS. Raises ValueError otherwise."""
    if value is None or value == "":
        return ALWAYS
    if not isinstance(value, str) or value.strip().lower() not in CONDITIONS:
        raise ValueError(f"appears must be one of: {', '.join(CONDITIONS)}")
    return value.strip().lower()


def sun_elevation(lat, lon, when):
    """Degrees of the sun above (+) or below (-) the horizon at this place and moment.

    when: an aware datetime (naive ones are taken as UTC). Accurate to about a degree,
    which is plenty to tell day from night.
    """
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    when = when.astimezone(timezone.utc)
    hours = when.hour + when.minute / 60 + when.second / 3600
    gamma = 2 * math.pi / 365 * (when.timetuple().tm_yday - 1 + (hours - 12) / 24)
    eq_time = 229.18 * (0.000075 + 0.001868 * math.cos(gamma) - 0.032077 * math.sin(gamma)
                        - 0.014615 * math.cos(2 * gamma) - 0.040849 * math.sin(2 * gamma))
    decl = (0.006918 - 0.399912 * math.cos(gamma) + 0.070257 * math.sin(gamma)
            - 0.006758 * math.cos(2 * gamma) + 0.000907 * math.sin(2 * gamma)
            - 0.002697 * math.cos(3 * gamma) + 0.00148 * math.sin(3 * gamma))
    solar_minutes = hours * 60 + eq_time + 4 * lon
    hour_angle = math.radians(solar_minutes / 4 - 180)
    phi = math.radians(lat)
    cos_zenith = (math.sin(phi) * math.sin(decl)
                  + math.cos(phi) * math.cos(decl) * math.cos(hour_angle))
    return 90 - math.degrees(math.acos(max(-1.0, min(1.0, cos_zenith))))


def is_dark(lat, lon, when):
    return sun_elevation(lat, lon, when) < DARK_BELOW_DEG


def is_raining(weather):
    """weather: weather.parse_weather's dict, or None when we don't know (then: not raining)."""
    if not weather:
        return False
    return weather.get("rain_mm", 0) >= RAIN_MM or weather.get("code") in RAIN_CODES


def is_visible(condition, raining, dark):
    if condition == RAIN:
        return raining
    if condition == NIGHT:
        return dark
    return True


def board_text(condition, visible_now, is_owner):
    """The line on the map's info board ("" for ordinary treasures)."""
    if condition == RAIN:
        what = "🌧 Rain treasure: it only appears while it is raining"
    elif condition == NIGHT:
        what = "🌙 Night treasure: it only appears after dark"
    else:
        return ""
    if is_owner and not visible_now:
        return what + ". Other players can't see it right now; you can, because you hid it."
    return what + "."


def saved_text(condition):
    """Added to "Saved ..." on the upload page ("" for ordinary treasures)."""
    if condition == RAIN:
        return "Other players will only see it while it is raining."
    if condition == NIGHT:
        return "Other players will only see it after dark."
    return ""


def hidden_text(condition):
    """Why a claim is refused when the treasure is not out right now."""
    if condition == RAIN:
        return "This treasure only appears in the rain. Come back when it is raining."
    if condition == NIGHT:
        return "This treasure only appears after dark. Come back tonight."
    raise ValueError(f"Not a hidden condition: {condition}")

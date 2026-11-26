"""Step-free (wheelchair-friendly) routes (owner: B).

Plain Python with no Flask and no database, so it is easy to test.
A player chooses on the Account page; route_access_api.py saves the choice, and the
route endpoints pass the matching OpenRouteService profile and settings to routing.py.

    walking     foot-walking: the normal walking routes
    wheelchair  ORS's wheelchair profile: avoids steps, and here also steep slopes and high kerbs
"""

WALKING = "walking"
WHEELCHAIR = "wheelchair"
CHOICES = (WALKING, WHEELCHAIR)

# Our choice -> the OpenRouteService profile name in the address.
ORS_PROFILES = {WALKING: "foot-walking", WHEELCHAIR: "wheelchair"}

# Limits for the wheelchair profile (see the ORS docs, "profile_params" > "restrictions").
MAX_INCLINE_PCT = 6        # steepest slope, in %
MAX_KERB_M = 0.06          # highest kerb to roll over, in metres
WHEELCHAIR_LIMITS = {"maximum_incline": MAX_INCLINE_PCT, "maximum_sloped_kerb": MAX_KERB_M}

LABELS = {WALKING: "Walking routes", WHEELCHAIR: "Step-free routes (wheelchair, buggy)"}


def parse_choice(data):
    """{"access": "walking" | "wheelchair"} -> the choice. Raises ValueError otherwise."""
    value = data.get("access") if isinstance(data, dict) else None
    if value not in CHOICES:
        raise ValueError(f"access must be one of: {', '.join(CHOICES)}")
    return value


def ors_profile(choice):
    return ORS_PROFILES.get(choice, ORS_PROFILES[WALKING])


def route_extra(choice, weather_extra):
    """The extra request settings for this choice, mixed with the weather's (weather.py).

    Walking: just the weather's. Wheelchair: the step-free limits, plus the weather's
    "shortest" in the rain. The weather's "greener" weighting is left out, because the
    wheelchair profile does not support it (ORS would refuse the whole request).
    """
    weather_extra = weather_extra or {}
    if choice != WHEELCHAIR:
        return weather_extra or None
    extra = {"options": {"profile_params": {"restrictions": dict(WHEELCHAIR_LIMITS)}}}
    if "preference" in weather_extra:
        extra["preference"] = weather_extra["preference"]
    return extra


def route_note(choice, used_service):
    """The note the map shows under a step-free route ("" for walking)."""
    if choice != WHEELCHAIR:
        return ""
    if used_service:
        return "♿ Step-free route: no steps, gentle slopes, low kerbs."
    return ("♿ No step-free route could be found right now, so this is a straight line. "
            "It may cross steps: check before you go.")

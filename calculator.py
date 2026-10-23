"""Steps and calories estimates for a walk. Owner: C."""

STEP_LENGTH_M = 0.75  # average walking step, in meters


def steps_from_distance(distance_m):
    """Return the estimated number of steps for a distance in meters."""
    if distance_m < 0:
        raise ValueError("distance_m cannot be negative")
    return round(distance_m / STEP_LENGTH_M)


def calories_from_distance(distance_m, weight_kg):
    """Return estimated calories burned for a walk.

    Formula: 0.5 x body weight (kg) x distance in KILOMETERS.
    """
    if distance_m < 0 or weight_kg < 0:
        raise ValueError("distance_m and weight_kg cannot be negative")
    distance_km = distance_m / 1000  # convert meters to kilometers
    return 0.5 * weight_kg * distance_km
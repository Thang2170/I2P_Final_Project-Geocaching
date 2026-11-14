"""Check the data a player sends when uploading a treasure. Owner: B.

Plain Python with no Flask and no database, so it is easy to test.
"""

from location import haversine_m

MAX_NAME_LENGTH = 100
MAX_DESCRIPTION_LENGTH = 300
# Two treasures closer than this would be found at the same time, so we don't allow it.
MIN_TREASURE_GAP_M = 10


def parse_number(value, field, low, high):
    """Turn value into a float between low and high, or raise ValueError."""
    if isinstance(value, bool) or value is None or str(value).strip() == "":
        raise ValueError(f"{field} is required")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field} must be a number") from None
    # "not in range" is also True for nan, so nan and inf are rejected here too
    if not low <= number <= high:
        raise ValueError(f"{field} must be between {low} and {high}")
    return number


def parse_treasure(data):
    """Return {"name", "description", "lat", "lon"} ready for the Treasure table.

    Raises ValueError with a message a player can read if anything is wrong.
    """
    if not isinstance(data, dict):
        raise ValueError("Send the treasure as JSON or form data")

    name = data.get("name") or ""
    description = data.get("description") or ""
    if not isinstance(name, str) or not isinstance(description, str):
        raise ValueError("name and description must be text")

    name = name.strip()
    description = description.strip()
    if not name:
        raise ValueError("name is required")
    if len(name) > MAX_NAME_LENGTH:
        raise ValueError(f"name must be at most {MAX_NAME_LENGTH} characters")
    if len(description) > MAX_DESCRIPTION_LENGTH:
        raise ValueError(f"description must be at most {MAX_DESCRIPTION_LENGTH} characters")

    return {
        "name": name,
        "description": description,
        "lat": parse_number(data.get("lat"), "lat", -90, 90),
        "lon": parse_number(data.get("lon"), "lon", -180, 180),
    }


def find_too_close(lat, lon, existing, min_distance_m=MIN_TREASURE_GAP_M):
    """Return the name of a treasure closer than min_distance_m, or None.

    existing is any list of (name, lat, lon) tuples.
    """
    for name, other_lat, other_lon in existing:
        if haversine_m(lat, lon, other_lat, other_lon) < min_distance_m:
            return name
    return None


def spot_problem(lat, lon, existing, min_distance_m=MIN_TREASURE_GAP_M):
    """A message a player can read if a new treasure can't go here, else None.

    The upload page asks this as soon as a spot is chosen on the map, and the
    upload itself asks it again before saving, so both always agree.
    """
    nearby = find_too_close(lat, lon, existing, min_distance_m)
    if nearby is None:
        return None
    return f'"{nearby}" is already hidden within {min_distance_m} m of this spot. Choose a different place.'

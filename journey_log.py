"""Rules for saving a finished hunt and ranking players (Feature 10, owner: B).

Plain Python with no Flask and no database, so it is easy to test.
journey_api.py uses these rules; the browser only sends what it measured.
"""

from treasure_input import parse_number

MAX_DISTANCE_M = 200_000        # same limit as the steps-and-calories endpoint
MAX_DURATION_S = 86_400         # one day
MAX_AVG_SPEED_MS = 6.0          # a fast run; quicker than this is a bike or a car, not a hunt on foot
MIN_PACE_DISTANCE_M = 20        # a pace is not shown for shorter walks (same as the map panel)
NO_PACE = "--:--"


def _parse_id(value, field):
    if isinstance(value, bool) or value is None or str(value).strip() == "":
        raise ValueError(f"{field} is required")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field} must be a whole number") from None
    if number != int(number) or number < 1:
        raise ValueError(f"{field} must be a whole number")
    return int(number)


def parse_journey(data):
    """Return {"treasure_id", "distance_m", "duration_s", "lat", "lon"} or raise ValueError.

    lat and lon are where the player stands when the hunt ends.
    """
    if not isinstance(data, dict):
        raise ValueError("Send the hunt as JSON")
    return {
        "treasure_id": _parse_id(data.get("treasure_id"), "treasure_id"),
        "distance_m": parse_number(data.get("distance_m"), "distance_m", 0, MAX_DISTANCE_M),
        "duration_s": int(round(parse_number(data.get("duration_s"), "duration_s", 1, MAX_DURATION_S))),
        "lat": parse_number(data.get("lat"), "lat", -90, 90),
        "lon": parse_number(data.get("lon"), "lon", -180, 180),
    }


def speed_problem(distance_m, duration_s):
    """A message if the hunt was too fast to be on foot, else None."""
    if distance_m / duration_s > MAX_AVG_SPEED_MS:
        return "That was too fast for a walk or a run, so it was not saved."
    return None


def format_duration(seconds):
    """Seconds as m:ss, or h:mm:ss from one hour on."""
    seconds = int(round(seconds))
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:02d}:{secs:02d}"


def format_pace(distance_m, duration_s):
    """Average pace as m:ss per km, or "--:--" when the walk was too short to tell."""
    if distance_m < MIN_PACE_DISTANCE_M or duration_s <= 0:
        return NO_PACE
    per_km = round(duration_s / (distance_m / 1000))
    if per_km >= 6000:
        return NO_PACE
    return f"{per_km // 60}:{per_km % 60:02d}"


def rank_players(rows):
    """Order players by hunts finished, then by distance walked, and give each a rank.

    rows: dicts with "username", "hunts" and "distance_m". Players with the same number of
    hunts and (to the nearest 10 m) the same distance share a rank; the next rank skips.
    Returns new dicts with "rank" added, best first.
    """
    ordered = sorted(rows, key=lambda r: (-r["hunts"], -r["distance_m"], r["username"].lower()))
    ranked, previous_key, previous_rank = [], None, 0
    for position, row in enumerate(ordered, start=1):
        key = (row["hunts"], round(row["distance_m"] / 10))
        rank = previous_rank if key == previous_key else position
        ranked.append({**row, "rank": rank})
        previous_key, previous_rank = key, rank
    return ranked

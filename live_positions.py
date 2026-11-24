"""Live player positions for the admin map (owner: A).

Plain Python with no Flask and no database, so it is easy to test.
Privacy: the server keeps only each player's LAST position, shows it only to admins,
and hides it once it is older than LIVE_WINDOW_S (the player closed the map or went offline).
"""

from datetime import timezone

from routing import check_point

LIVE_WINDOW_S = 120  # older than 2 minutes: the player is not on the map any more


def as_utc(when):
    """SQLite gives times back without a zone. We always save UTC, so say so."""
    if when.tzinfo is None:
        return when.replace(tzinfo=timezone.utc)
    return when


def seconds_ago(updated_at, now):
    """How many whole seconds ago a position was saved."""
    return int((as_utc(now) - as_utc(updated_at)).total_seconds())


def is_live(updated_at, now, window_s=LIVE_WINDOW_S):
    """True if the position is recent enough to show on the admin map."""
    return seconds_ago(updated_at, now) <= window_s


def parse_position(data):
    """Turn the JSON the phone sends ({"lat": .., "lon": ..}) into (lat, lon).

    Raises ValueError with a clear message if it is missing or not a real place.
    """
    if not isinstance(data, dict):
        raise ValueError("Send JSON with lat and lon")
    return check_point((data.get("lat"), data.get("lon")))

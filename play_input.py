"""Shared input checks for the new ways to play (owner: B). Plain Python, no Flask, no database."""

from treasure_input import parse_number


def parse_position(data):
    """(lat, lon) from {"lat": .., "lon": ..}. Raises ValueError with a message for the player."""
    if not isinstance(data, dict):
        raise ValueError("Send your lat and lon")
    return parse_number(data.get("lat"), "lat", -90, 90), parse_number(data.get("lon"), "lon", -180, 180)


def parse_seconds(value, field="elapsed_s", most=6 * 3600):
    """A number of seconds from 0 to `most`. Raises ValueError."""
    return parse_number(value, field, 0, most)


def may_manage(user_id, creator_id, admin):
    """Only the player who hid a treasure (or an admin) may add a box or a team lock to it."""
    return admin or (creator_id is not None and user_id == creator_id)

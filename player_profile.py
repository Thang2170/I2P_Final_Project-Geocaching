"""Rules for a player's public profile page (owner: B).

Plain Python with no Flask and no database, so it is easy to test.
profile_api.py gathers the numbers from the database and uses these rules to shape them.
"""

from leaderboard import rank_players
from user_input import USERNAME_PATTERN

RECENT_HUNTS = 5       # finished hunts shown on a profile
RECENT_POSTS = 5       # written posts shown on a profile
HIDDEN_SHOWN = 10      # treasures they hid, shown by name


def parse_username(value):
    """The username from the page address, or raise ValueError.

    Usernames only use letters, digits and _ (see user_input.py), so anything else
    can't be a player and is refused before it reaches the database.
    """
    if not isinstance(value, str) or not USERNAME_PATTERN.fullmatch(value):
        raise ValueError("No such player")
    return value


def rank_of(username, rows):
    """(rank, how many players) on the same leaderboard as /leaderboard, or (None, n) if not found.

    rows: every player as {"username", "coins", "found", "hidden"}.
    """
    ranked = rank_players(rows, limit=len(rows))
    for player in ranked:
        if player["username"] == username:
            return player["rank"], len(ranked)
    return None, len(ranked)


def joined_label(created_at):
    """'Joined 14 Nov 2026'."""
    return f"Joined {created_at.day} {created_at.strftime('%b %Y')}"


def walk_totals(journeys):
    """Totals over a player's finished hunts.

    journeys: (distance_m, steps) for each finished hunt.
    """
    distance_m = sum(d for d, _ in journeys)
    return {
        "hunts": len(journeys),
        "distance_km": round(distance_m / 1000, 2),
        "steps": sum(s for _, s in journeys),
    }

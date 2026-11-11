"""Rank players for the leaderboard (owner: A).

Plain Python with no Flask and no database, so it is easy to test.
"""

TOP_PLAYERS = 20


def rank_players(players, limit=TOP_PLAYERS):
    """Sort players by coins, then by treasures found, and number them from 1.

    players is a list of dicts with "username", "coins", "found" and "hidden".
    Returns a new list of at most `limit` dicts, each with a "rank" added.
    """
    ordered = sorted(players, key=lambda p: (-p["coins"], -p["found"], p["username"].lower()))
    ranked = []
    for position, player in enumerate(ordered[:limit], start=1):
        ranked.append({**player, "rank": position})
    return ranked

"""Who is playing and who is waiting in a hunt (Feature 8, owner: B).

Plain Python with no Flask and no database, so it is easy to test.

A hunt has a capacity. Players are listed in the order they joined: the first
`capacity` of them are playing and everyone after that waits in line. Nobody's
status is stored, it is worked out from the order, so when a player leaves the
next one in line moves up by itself.
"""

PLAYING = "playing"
WAITING = "waiting"


def count_players(member_count, capacity):
    """Return (playing, waiting) for a hunt with this many members."""
    playing = min(member_count, capacity)
    return playing, member_count - playing


def queue_status(user_id, member_ids, capacity):
    """Where this player is in the hunt.

    member_ids: the ids of everyone in the hunt, in the order they joined.
    Returns None if the player is not in the hunt, otherwise
    {"state": "playing" or "waiting", "position": n}. Playing positions count
    from 1; waiting positions count from 1 for the first player in line.
    """
    if user_id not in member_ids:
        return None
    index = member_ids.index(user_id)
    if index < capacity:
        return {"state": PLAYING, "position": index + 1}
    return {"state": WAITING, "position": index - capacity + 1}


def status_text(status, finished=False):
    """B: the "you" line on a hunt card. status: queue_status()'s dict (not None).

    finished: the hunt's race is over, so nobody is "playing" or "waiting" any more.
    """
    if finished:
        return "You raced in this hunt" if status["state"] == PLAYING else "You were in line for this race"
    if status["state"] == PLAYING:
        return f"You are playing (#{status['position']})"
    return f"You are waiting: #{status['position']} in line"

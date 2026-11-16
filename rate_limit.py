"""Anti-spam: a short wait between posts, comments and chat messages (owner: B).

Plain Python with no Flask and no database, so it is easy to test.
feed_api.py and chat_api.py look up when you last sent something, and ask wait_left().
"""

from datetime import timezone

# The shortest gap, in seconds, between two things of the same kind from the same player.
MIN_GAP_S = {
    "post": 10,      # a new post on the Community feed
    "comment": 3,    # a comment under a post
    "reply": 3,      # a reply to a comment (B: replies)
    "chat": 1,       # a message in a hunt's group chat (short: chats are quick back-and-forth)
}


def _utc(moment):
    # SQLite gives back times without a time zone; they were saved in UTC.
    return moment.replace(tzinfo=timezone.utc) if moment.tzinfo is None else moment


def wait_left(last_sent, now, min_gap_s):
    """Whole seconds still to wait before sending again (0 means "go ahead").

    last_sent: when this player last sent one of these, or None if never.
    """
    if last_sent is None or min_gap_s <= 0:
        return 0
    passed = (_utc(now) - _utc(last_sent)).total_seconds()
    if passed >= min_gap_s:
        return 0
    left = min_gap_s - passed
    return max(1, int(left) + (1 if left % 1 else 0))  # round up: "wait 0 s" would be confusing


def slow_down_message(seconds):
    """What the player reads when they are too quick."""
    unit = "second" if seconds == 1 else "seconds"
    return f"Slow down a little: you can send again in {seconds} {unit}."

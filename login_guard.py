"""Stop people from guessing passwords (owner: B).

Plain Python with no Flask and no database, so it is easy to test.
auth_api.py saves every wrong login (LoginFailure) and asks these rules whether to let the
next try through.

    After MAX_FAILS wrong passwords for the same username from the same place within WINDOW_S,
    that username is locked there until the oldest of those tries is WINDOW_S old.
    A right password clears the count.

Counting per username AND place means a stranger elsewhere can't lock the real player out.
A username that doesn't exist is counted the same way, so the answers never reveal which
usernames exist.
"""

import math

MAX_FAILS = 5
WINDOW_S = 10 * 60


def recent_fails(fail_times, now):
    """The wrong tries that still count (the last WINDOW_S), oldest first."""
    return sorted(t for t in fail_times if 0 <= (now - t).total_seconds() < WINDOW_S)


def locked_for(fail_times, now):
    """Seconds until the next try is allowed (0 = allowed now)."""
    recent = recent_fails(fail_times, now)
    if len(recent) < MAX_FAILS:
        return 0
    oldest_that_counts = recent[-MAX_FAILS]
    return max(0, math.ceil(WINDOW_S - (now - oldest_that_counts).total_seconds()))


def lock_text(seconds):
    """What the player reads while locked."""
    minutes = max(1, math.ceil(seconds / 60))
    return f"Too many wrong passwords. Try again in {minutes} minute{'s' if minutes != 1 else ''}."


def tries_left_text(fails_now):
    """Added to "Wrong username or password" once a lock is getting close ("" before that)."""
    left = MAX_FAILS - fails_now
    if left <= 0 or left > 2:
        return ""
    return f" {left} more tr{'y' if left == 1 else 'ies'} before a {WINDOW_S // 60}-minute wait."

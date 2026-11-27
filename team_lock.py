"""Team treasures: some treasures only open when 2 or 3 players stand at them in the same minute (owner: B).

You cannot open one alone, so you have to message friends and meet up there. Each player
taps "I'm here" at the treasure; when enough different players did so within WINDOW_S, the
lock opens for all of them, and each can then find the treasure as normal (plus a team bonus).

Plain Python with no Flask and no database, so it is easy to test.
"""

NEEDS = (2, 3)
WINDOW_S = 60
TEAM_BONUS = 15
NEED_PROBLEM = "A team treasure needs 2 or 3 players."


def parse_need(value):
    """2 or 3. Raises ValueError otherwise."""
    if isinstance(value, bool):
        raise ValueError(NEED_PROBLEM)
    try:
        need = int(value)
    except (TypeError, ValueError):
        raise ValueError(NEED_PROBLEM) from None
    if need not in NEEDS or str(value).strip() not in {str(n) for n in NEEDS}:
        raise ValueError(NEED_PROBLEM)
    return need


def here_now(checkins, now, window_s=WINDOW_S):
    """The players who tapped "I'm here" in the last window_s seconds. checkins: [(user_id, when)]."""
    return {user_id for user_id, when in checkins if 0 <= (now - when).total_seconds() <= window_s}


def who_opens(need, here_ids, opened_ids):
    """The players the lock opens for now: everyone here, once enough are here (minus who already opened it)."""
    if len(here_ids) < need:
        return set()
    return set(here_ids) - set(opened_ids)


def status_text(need, here_count, opened_by_me):
    if opened_by_me:
        return "Open! You can find this treasure now."
    missing = need - here_count
    if missing <= 0:
        return "Everyone is here. Tap \"I'm here\" to open it."
    if here_count == 0:
        return f"Needs {need} players here within a minute of each other."
    friends = "1 more player" if missing == 1 else f"{missing} more players"
    return f"{here_count} of {need} here. {friends} must tap \"I'm here\" within a minute."


def claim_refusal_text(need):
    return (f"This is a team treasure: it opens only when {need} players are at it together. "
            "Open it on the Team page first.")

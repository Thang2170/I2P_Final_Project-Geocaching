""""Didn't find it" reports, like the DNF logs of real geocaching (owner: B).

Plain Python with no Flask and no database, so it is easy to test.
dnf_api.py saves the reports and asks these rules what they mean.

    A player who walked to a treasure and looked, but could not find it, says so.
    When MISSING_AFTER different players have said so since the treasure was last found,
    the map marks it "maybe missing" and its owner gets a notification once.
    The next real find clears it: only reports made after the last find count.
"""

MISSING_AFTER = 3          # different players since the last find
REPORT_RADIUS_M = 60       # you must be this close: you looked at the spot (GPS is not exact)

OWN = "own"
TOO_FAR = "too_far"
ALREADY = "already"


def report_problem(is_owner, distance_m, already_reported):
    """Why this report is refused (OWN, TOO_FAR or ALREADY), or None if it is fine."""
    if is_owner:
        return OWN
    if distance_m > REPORT_RADIUS_M:
        return TOO_FAR
    if already_reported:
        return ALREADY
    return None


def problem_text(problem, distance_m=0):
    """What the player reads when a report is refused."""
    if problem == OWN:
        return "This is your own treasure. If it is gone, hide it again or tell an admin."
    if problem == TOO_FAR:
        return (f"You are {round(distance_m)} m away. Walk to the spot and look first "
                f"(within {REPORT_RADIUS_M} m).")
    if problem == ALREADY:
        return "You already said you couldn't find this one. Thanks, we counted it."
    raise ValueError(f"Unknown problem: {problem}")


def open_reporters(reports, last_find_at):
    """The players whose report still counts: made after the last find (all, if never found).

    reports: (user_id, when) pairs. last_find_at: when it was last found, or None.
    """
    return {uid for uid, when in reports if last_find_at is None or when > last_find_at}


def is_missing(count):
    return count >= MISSING_AFTER


def just_went_missing(before, after):
    """True only for the report that tips it over, so the owner is told once."""
    return before < MISSING_AFTER <= after


def board_text(count):
    """The line on the map's info board ("" when nobody reported it)."""
    if count <= 0:
        return ""
    if is_missing(count):
        return (f"Maybe missing: {count} players couldn't find it since it was last found. "
                "You can still look, and finding it clears this.")
    people = "1 player" if count == 1 else f"{count} players"
    return f"{people} couldn't find it lately. Look carefully."


def thanks_text(count):
    """What the reporter reads after a report is saved."""
    if is_missing(count):
        return "Thanks. It is now marked maybe missing, and its owner has been told."
    left = MISSING_AFTER - count
    return (f"Thanks for telling us. {left} more player{'s' if left != 1 else ''} "
            "and it gets marked maybe missing.")


def owner_text(treasure_name, count):
    """The bell notification for the treasure's owner."""
    return (f'{count} players couldn\'t find your treasure "{treasure_name}". '
            "Check that it is still there.")

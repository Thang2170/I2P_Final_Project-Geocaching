"""Coin rules for the treasure hunt (Feature 9, owner: B).

Plain Python with no Flask and no database, so it is easy to test.
A player earns coins by finding a treasure: standing within FOUND_RADIUS_M of it.
"""

from location import FOUND_RADIUS_M

COINS_PER_FIND = 10

# Why a claim can be refused. coin_api.py turns each code into a message.
OWN_TREASURE = "own"          # you cannot earn coins from a treasure you hid yourself
ALREADY_FOUND = "already"     # each treasure pays a player only once
TOO_FAR = "far"               # not within FOUND_RADIUS_M


def claim_problem(distance_m, user_id, treasure_creator_id, already_found):
    """Return the reason a claim must be refused, or None if it is allowed.

    distance_m: how far the player is from the treasure, in meters
    treasure_creator_id: the id of the player who hid it (None for the demo treasure)
    already_found: True if this player was already paid for this treasure
    """
    if treasure_creator_id is not None and treasure_creator_id == user_id:
        return OWN_TREASURE
    if already_found:
        return ALREADY_FOUND
    if distance_m > FOUND_RADIUS_M:
        return TOO_FAR
    return None


def first_to_find(treasure_ids, found_ids):
    """Which treasure the map should aim at first: the oldest one this player hasn't found.

    treasure_ids: every treasure, oldest first. found_ids: the ones this player was paid for.
    If they have found them all, it falls back to the oldest one. None if there are no treasures.
    """
    found = set(found_ids)
    for treasure_id in treasure_ids:
        if treasure_id not in found:
            return treasure_id
    return treasure_ids[0] if treasure_ids else None

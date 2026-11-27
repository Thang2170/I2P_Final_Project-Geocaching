"""Traveling treasures: things that players carry from one treasure to the next (owner: B).

A player releases a traveler (say "the Golden Duck") at a treasure and may give it a goal,
another treasure it wants to reach. Anyone standing at the treasure can pick it up, carry it
and drop it at another treasure. Its page shows every stop and who carried it, and the
player who drops it at its goal gets a bonus. Strangers play it together, as a relay.

Where a traveler is comes from its moves only (the last one wins), so nothing is overwritten:
release (at a treasure), pick (into a player's bag), drop (at a treasure).

Plain Python with no Flask and no database, so it is easy to test.
"""

from location import FOUND_RADIUS_M, haversine_m

RELEASE, PICK, DROP = "release", "pick", "drop"
NAME_MIN, NAME_MAX = 3, 30
MAX_RELEASED = 3     # travelers one player may release
MAX_CARRIED = 1      # travelers one player may carry at a time
GOAL_BONUS = 25

AT_TREASURE, IN_BAG = "treasure", "bag"

NOT_NEAR = f"Stand at a treasure (within {FOUND_RADIUS_M} m) first."
TAKEN = "Someone is carrying it right now."
NOT_HERE = "It is not at this treasure."
FULL_BAG = "You are already carrying a traveler. Drop it somewhere first."
NOT_YOURS = "You are not carrying it."
SAME_PLACE = "Take it somewhere new: drop it at a different treasure."
TOO_MANY = f"You can release {MAX_RELEASED} travelers at most."


def parse_traveler(data, treasure_ids):
    """(name, goal_treasure_id or None). Raises ValueError with a message for the player."""
    if not isinstance(data, dict):
        raise ValueError("Send a name for your traveler")
    name = " ".join(str(data.get("name") or "").split())
    if not NAME_MIN <= len(name) <= NAME_MAX:
        raise ValueError(f"The name needs {NAME_MIN} to {NAME_MAX} letters")
    goal = data.get("goal_treasure_id")
    if goal in (None, ""):
        return name, None
    if isinstance(goal, bool) or not isinstance(goal, int) or goal not in treasure_ids:
        raise ValueError("Pick a treasure for its goal, or leave the goal empty")
    return name, goal


def nearest_treasure(lat, lon, treasures):
    """The closest treasure within FOUND_RADIUS_M, as (id, distance), or None. treasures: [(id, lat, lon)]."""
    best = None
    for treasure_id, t_lat, t_lon in treasures:
        distance = haversine_m(lat, lon, t_lat, t_lon)
        if distance <= FOUND_RADIUS_M and (best is None or distance < best[1]):
            best = (treasure_id, distance)
    return best


def where_is(moves):
    """Where the traveler is now. moves: [(action, user_id, treasure_id)] oldest first."""
    action, user_id, treasure_id = moves[-1]
    if action == PICK:
        return {"where": IN_BAG, "user_id": user_id}
    return {"where": AT_TREASURE, "treasure_id": treasure_id}


def last_place(moves):
    """The treasure it was last left at (picking it up does not change this)."""
    return next((t for action, _, t in reversed(moves) if action in (RELEASE, DROP)), None)


def pick_problem(moves, me, here_treasure_id, carrying):
    """None if `me` may pick it up at here_treasure_id (None = not at a treasure)."""
    if here_treasure_id is None:
        return NOT_NEAR
    now = where_is(moves)
    if now["where"] == IN_BAG:
        return TAKEN
    if now["treasure_id"] != here_treasure_id:
        return NOT_HERE
    if carrying >= MAX_CARRIED:
        return FULL_BAG
    return None


def drop_problem(moves, me, here_treasure_id):
    """None if `me` may drop it at here_treasure_id."""
    now = where_is(moves)
    if now["where"] != IN_BAG or now["user_id"] != me:
        return NOT_YOURS
    if here_treasure_id is None:
        return NOT_NEAR
    if here_treasure_id == last_place(moves):
        return SAME_PLACE
    return None


def release_problem(here_treasure_id, released):
    if here_treasure_id is None:
        return NOT_NEAR
    return TOO_MANY if released >= MAX_RELEASED else None


def stops(moves):
    """The treasures it was left at, in order (release and every drop)."""
    return [t for action, _, t in moves if action in (RELEASE, DROP)]


def reached_goal(moves, goal_id):
    """The index of the move that first dropped it at its goal, or None."""
    if goal_id is None:
        return None
    return next((i for i, (action, _, t) in enumerate(moves) if action == DROP and t == goal_id), None)


def journey_m(places):
    """How far it travelled: the straight lines between its stops. places: [(lat, lon)]."""
    return round(sum(haversine_m(a[0], a[1], b[0], b[1]) for a, b in zip(places, places[1:])))


def distance_text(metres):
    return f"{metres} m" if metres < 1000 else f"{metres / 1000:.1f} km"

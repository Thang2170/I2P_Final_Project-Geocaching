"""Hunt race rules (owner: A): a hunt is a race to one treasure.

Plain Python with no Flask and no database, so it is easy to test.
hunt_game_api.py saves the game and uses these rules to decide what is allowed.

    open      players join; the creator picks the treasure when making the hunt
    started   the creator pressed Start: no new players, everyone playing races to the treasure
    finished  the first playing member within FOUND_RADIUS_M of the treasure won
"""

from location import FOUND_RADIUS_M

OPEN = "open"
STARTED = "started"
FINISHED = "finished"

WIN_BONUS = 20            # extra coins for winning a hunt race
WIN_REASON = "hunt_win"   # how the bonus shows up in the coin ledger


def game_state(started_at, winner_id):
    """Work out the state from what is saved, so it can never disagree with the data."""
    if winner_id is not None:
        return FINISHED
    if started_at is not None:
        return STARTED
    return OPEN


def start_problem(user_id, creator_id, is_playing, state):
    """Why this player may not start the hunt, or None if they may.

    creator_id is None for the demo hunts: then any playing member may start them.
    The hunt does not have to be full: 1 playing member is enough.
    """
    if state != OPEN:
        return "This hunt has already started."
    if creator_id is not None and user_id != creator_id:
        return "Only the player who made this hunt can start it."
    if not is_playing:
        return "Join the hunt (and be playing, not waiting) before you start it."
    return None


def join_problem(state):
    """Nobody new can join a race that is already running or finished."""
    if state != OPEN:
        return "This hunt has already started, so you can't join it now."
    return None


def win_problem(state, is_playing, distance_m):
    """Why this arrival does not win the race, or None if it does."""
    if state == OPEN:
        return "The hunt has not started yet."
    if state == FINISHED:
        return "Someone already won this hunt."
    if not is_playing:
        return "Only players in the hunt can win (not the waiting line)."
    if distance_m > FOUND_RADIUS_M:
        return f"Get within {FOUND_RADIUS_M} m of the treasure ({round(distance_m)} m away)."
    return None

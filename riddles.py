"""Riddle chains: treasures found in order, each riddle unlocking the next (owner: B).

Plain Python with no Flask and no database, so it is easy to test.

A chain is 2 to MAX_STEPS treasures, each with a riddle that leads to it. Only the first riddle
is shown at the start; finding a step's treasure unlocks the next riddle. Finding the whole
chain pays CHAIN_BONUS coins once. Python decides what is visible, so a locked riddle is never
sent to the browser.
"""

MIN_STEPS, MAX_STEPS = 2, 6
TITLE_MIN, TITLE_MAX = 3, 60
CLUE_MIN, CLUE_MAX = 3, 200
CHAIN_BONUS = 25

FOUND, CURRENT, LOCKED = "found", "current", "locked"


def _text(value, field, low, high):
    if not isinstance(value, str):
        raise ValueError(f"{field} must be text")
    text = " ".join(value.split())  # no runs of spaces or new lines
    if not low <= len(text) <= high:
        raise ValueError(f"{field} must be {low} to {high} characters")
    return text


def parse_chain(data, treasure_ids):
    """Check a new chain. Send {"title": .., "steps": [{"treasure_id": .., "clue": ..}, ...]}.

    treasure_ids: the treasures that exist. Returns (title, [(treasure_id, clue), ...]).
    Raises ValueError with a message the player can read.
    """
    if not isinstance(data, dict):
        raise ValueError("Send the chain as JSON")
    title = _text(data.get("title"), "The title", TITLE_MIN, TITLE_MAX)
    steps = data.get("steps")
    if not isinstance(steps, list) or not MIN_STEPS <= len(steps) <= MAX_STEPS:
        raise ValueError(f"A chain has {MIN_STEPS} to {MAX_STEPS} steps")
    known = set(treasure_ids)
    out = []
    for n, step in enumerate(steps, start=1):
        if not isinstance(step, dict):
            raise ValueError(f"Step {n} is not filled in")
        tid = step.get("treasure_id")
        if isinstance(tid, bool) or not isinstance(tid, int) or tid not in known:
            raise ValueError(f"Step {n}: choose a treasure")
        if tid in (t for t, _ in out):
            raise ValueError(f"Step {n}: that treasure is already in the chain")
        out.append((tid, _text(step.get("clue"), f"Step {n}'s riddle", CLUE_MIN, CLUE_MAX)))
    return title, out


def step_states(step_ids, found_ids):
    """FOUND / CURRENT / LOCKED for each step, in order.

    Steps are solved in order: a step is FOUND only if it and every step before it was found.
    The first step not solved yet is CURRENT (its riddle is shown); the rest are LOCKED. If you
    happen to find a later treasure first, it counts when you reach it.
    """
    found = set(found_ids)
    states, open_ = [], True
    for tid in step_ids:
        if open_ and tid in found:
            states.append(FOUND)
        elif open_:
            states.append(CURRENT)
            open_ = False
        else:
            states.append(LOCKED)
    return states


def is_complete(step_ids, found_ids):
    return all(state == FOUND for state in step_states(step_ids, found_ids))

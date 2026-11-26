"""Rain and night treasures (owner: B). The rules live in conditions.py.

No pages or endpoints of its own: these helpers are used where treasures are listed,
aimed at, planned into trails and claimed, so a hidden treasure is hidden everywhere.

    save_condition()   the upload form's "When can players see it?" choice
    hidden_ids()       treasures this player can't see right now
    appears_info()     the board line for each rain or night treasure
    claim_refusal()    why a claim is refused while the treasure is not out
"""

from datetime import datetime, timezone

from conditions import ALWAYS, board_text, hidden_text, is_dark, is_raining, is_visible
from models import TreasureCondition, db
from weather_api import weather_for


def _now():
    return datetime.now(timezone.utc)


def save_condition(treasure_id, condition):
    """Save a rain or night condition for a new treasure (nothing for ALWAYS). Caller commits."""
    if condition != ALWAYS:
        db.session.add(TreasureCondition(treasure_id=treasure_id, condition=condition))


def conditions_by_id():
    return dict(db.session.execute(db.select(TreasureCondition.treasure_id, TreasureCondition.condition)).all())


def visible_now(condition, treasure, now=None):
    """Is this rain or night treasure out right now, at its own spot?"""
    weather = weather_for(treasure.lat, treasure.lon)[0] if condition == "rain" else None
    return is_visible(condition, is_raining(weather), is_dark(treasure.lat, treasure.lon, now or _now()))


def hidden_ids(treasures, user_id, conditions=None):
    """Ids of the treasures this player can't see now. You always see the ones you hid."""
    conditions = conditions_by_id() if conditions is None else conditions
    now = _now()
    return {t.id for t in treasures
            if t.id in conditions and t.created_by != user_id and not visible_now(conditions[t.id], t, now)}


def appears_info(treasures, user_id, conditions=None):
    """{treasure id: {"condition", "text"}} for the rain and night treasures in this list."""
    conditions = conditions_by_id() if conditions is None else conditions
    now = _now()
    out = {}
    for t in treasures:
        condition = conditions.get(t.id)
        if condition:
            out[t.id] = {"condition": condition,
                         "text": board_text(condition, visible_now(condition, t, now), t.created_by == user_id)}
    return out


def claim_refusal(treasure, user_id):
    """The message refusing a claim while the treasure is hidden, or None."""
    condition = conditions_by_id().get(treasure.id)
    if condition is None or treasure.created_by == user_id or visible_now(condition, treasure):
        return None
    return hidden_text(condition)

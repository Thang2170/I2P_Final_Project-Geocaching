"""How many coins a treasure is worth right now: supply and demand (owner: B).

Plain Python with no Flask and no database, so it is easy to test.

Every treasure starts at BASE_COINS (the old fixed 10). Then:
- a treasure nobody has found for a while grows a bounty: +IDLE_BONUS_PER_DAY a day, up to
  +MAX_IDLE_BONUS. Days count from its last find, or from when it was hidden if never found;
- a treasure many people found this week gets cheaper: -1 for each find this week beyond
  FREE_FINDS_PER_WEEK.
The result stays between MIN_COINS and MAX_COINS. So players spread out over the whole campus
instead of everyone walking to the same three spots.
"""

from datetime import timezone

BASE_COINS = 10
MIN_COINS, MAX_COINS = 5, 30
IDLE_BONUS_PER_DAY = 2
MAX_IDLE_BONUS = MAX_COINS - BASE_COINS
FREE_FINDS_PER_WEEK = 2
WEEK_S = 7 * 24 * 3600

BOUNTY_FROM = 20   # worth this much or more: shown as a bounty
POPULAR_UP_TO = 7  # worth this much or less: shown as popular


def as_utc(when):
    """SQLite gives times back without a zone. We always save UTC, so say so."""
    return when.replace(tzinfo=timezone.utc) if when.tzinfo is None else when


def coins_for(hidden_at, find_times, now):
    """What a find pays now. hidden_at: when the treasure was hidden. find_times: when it was found."""
    now = as_utc(now)
    finds = [as_utc(t) for t in find_times]
    last = max(finds) if finds else as_utc(hidden_at)
    idle_days = max(0, int((now - last).total_seconds() // 86400))
    bonus = min(MAX_IDLE_BONUS, IDLE_BONUS_PER_DAY * idle_days)
    this_week = sum(1 for t in finds if 0 <= (now - t).total_seconds() <= WEEK_S)
    crowd = max(0, this_week - FREE_FINDS_PER_WEEK)
    return max(MIN_COINS, min(MAX_COINS, BASE_COINS + bonus - crowd))


def label(coins):
    """A short word for the map: "bounty", "popular" or "" (normal)."""
    if coins >= BOUNTY_FROM:
        return "bounty"
    if coins <= POPULAR_UP_TO:
        return "popular"
    return ""


def explain(coins):
    """One line for the treasure's info board."""
    kind = label(coins)
    if kind == "bounty":
        return f"Worth {coins} coins: nobody has found it for a while!"
    if kind == "popular":
        return f"Worth {coins} coins: lots of players found it this week."
    return f"Worth {coins} coins."

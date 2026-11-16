"""Rules for rating treasures and for the "Top rated" and "Trending this week" lists (owner: B).

Plain Python with no Flask and no database, so it is easy to test.
rating_api.py gathers the numbers from the database and uses these rules.
"""

from datetime import timedelta, timezone

MIN_STARS = 1
MAX_STARS = 5

# "Top rated" uses a weighted average: every treasure starts as if PRIOR_COUNT players had given
# it PRIOR_MEAN stars. So one lonely 5-star rating can't beat twenty ratings averaging 4.8.
PRIOR_MEAN = 3.5
PRIOR_COUNT = 3

TRENDING_DAYS = 7     # "this week"
LIST_SIZE = 6         # how many treasures each list shows


def parse_stars(data):
    """The stars a player gave (a whole number from 1 to 5), or raise ValueError."""
    stars = data.get("stars") if isinstance(data, dict) else None
    if isinstance(stars, bool) or not isinstance(stars, int):
        raise ValueError(f"Give {MIN_STARS} to {MAX_STARS} stars")
    if not MIN_STARS <= stars <= MAX_STARS:
        raise ValueError(f"Give {MIN_STARS} to {MAX_STARS} stars")
    return stars


def can_rate(treasure_id, found_ids):
    """Only players who found a treasure may rate it, so nobody rates a place they never went to."""
    return treasure_id in set(found_ids)


def summary(stars_sum, count):
    """{"average": 4.6, "count": 12} for showing next to a treasure (average None when unrated)."""
    return {"average": round(stars_sum / count, 1) if count else None, "count": count}


def weighted_score(stars_sum, count):
    """The number "Top rated" sorts by (see PRIOR_MEAN above)."""
    return (PRIOR_MEAN * PRIOR_COUNT + stars_sum) / (PRIOR_COUNT + count)


def top_rated(rows, limit=LIST_SIZE):
    """The best-loved treasures, best first. Only treasures with at least one rating.

    rows: {"id", "stars_sum", "count"} for each treasure.
    """
    rated = [r for r in rows if r["count"] > 0]
    rated.sort(key=lambda r: (-weighted_score(r["stars_sum"], r["count"]), -r["count"], r["id"]))
    return [r["id"] for r in rated[:limit]]


def _utc(moment):
    # SQLite gives back times without a time zone; they were saved in UTC.
    return moment.replace(tzinfo=timezone.utc) if moment.tzinfo is None else moment


def trending_score(event_times, now, days=TRENDING_DAYS):
    """How "hot" a treasure is: its finds and ratings in the last `days`, newer ones counting more.

    Something that happened just now counts 1; a week ago it counts almost nothing.
    """
    window = timedelta(days=days).total_seconds()
    score = 0.0
    for moment in event_times:
        age = (_utc(now) - _utc(moment)).total_seconds()
        if 0 <= age < window:
            score += 1 - age / window
    return score


def trending(events_by_treasure, now, limit=LIST_SIZE):
    """The treasures people are finding and rating right now, hottest first.

    events_by_treasure: {treasure id: [times of its finds and ratings]}.
    Treasures with nothing in the last week are left out.
    """
    scored = [(trending_score(times, now), tid) for tid, times in events_by_treasure.items()]
    scored = [(s, tid) for s, tid in scored if s > 0]
    scored.sort(key=lambda pair: (-pair[0], pair[1]))
    return [tid for _, tid in scored[:limit]]


def newest_unrated(treasure_ids, rated_ids, limit=LIST_SIZE):
    """Treasures nobody has rated yet, newest first. The welcome page shows them as "New!"
    after the top rated ones, so a fresh treasure still gets seen."""
    rated = set(rated_ids)
    return sorted((t for t in treasure_ids if t not in rated), reverse=True)[:limit]

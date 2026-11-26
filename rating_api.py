"""Treasure ratings, and the "Top rated" and "Trending this week" lists (owner: B).

Rules live in ratings.py. Like route_api.py, this lives in its own Blueprint.
- POST /api/treasures/<id>/rating   rate a treasure you found (JSON: stars)
- GET  /api/treasures/rankings      the two lists for the welcome page
/api/treasures (treasure_api.py) also shows each treasure's rating, using rating_summaries().
"""

from datetime import datetime, timedelta, timezone

from flask import Blueprint, jsonify, request
from sqlalchemy.exc import IntegrityError

from auth_api import current_user
from coin_api import FOUND_REASON, found_treasure_ids
from models import CoinTransaction, Treasure, TreasureRating, db
from ratings import TRENDING_DAYS, can_rate, newest_unrated, parse_stars, summary, top_rated, trending

rating_api = Blueprint("rating_api", __name__)


def rating_summaries():
    """{treasure id: {"average", "count", "stars_sum"}} for every rated treasure."""
    rows = db.session.execute(db.select(
        TreasureRating.treasure_id, db.func.sum(TreasureRating.stars), db.func.count(TreasureRating.id)
    ).group_by(TreasureRating.treasure_id)).all()
    return {tid: {**summary(total, count), "stars_sum": total} for tid, total, count in rows}


def my_ratings(user_id):
    """{treasure id: stars} for what this player rated."""
    rows = db.session.execute(db.select(TreasureRating.treasure_id, TreasureRating.stars).where(
        TreasureRating.user_id == user_id)).all()
    return dict(rows)


@rating_api.route("/api/treasures/<int:treasure_id>/rating", methods=["POST"])
def rate(treasure_id):
    """Rate a treasure 1-5 stars. Only after you found it; rating again changes your stars."""
    user = current_user()
    if user is None:
        return jsonify(error="Log in first"), 401
    treasure = db.session.get(Treasure, treasure_id)
    if treasure is None:
        return jsonify(error="No such treasure"), 404
    try:
        stars = parse_stars(request.get_json(silent=True))
    except ValueError as err:
        return jsonify(error=str(err)), 400
    if not can_rate(treasure_id, found_treasure_ids(user.id)):
        return jsonify(error="Find this treasure first, then you can rate it."), 403

    mine = db.session.execute(db.select(TreasureRating).where(
        TreasureRating.user_id == user.id, TreasureRating.treasure_id == treasure_id)).scalar_one_or_none()
    if mine is None:
        db.session.add(TreasureRating(user_id=user.id, treasure_id=treasure_id, stars=stars))
    else:
        mine.stars = stars
    try:
        db.session.commit()
    except IntegrityError:  # a double tap: the first tap already saved it
        db.session.rollback()

    info = rating_summaries().get(treasure_id, {"average": None, "count": 0})
    return jsonify(treasure_id=treasure_id, mine=stars, average=info["average"], count=info["count"])


@rating_api.route("/api/treasures/rankings")
def rankings():
    """The welcome page's rows: Top rated, Trending this week, and New (not rated yet).
    Anyone can see these."""
    treasures = {t.id: t for t in db.session.execute(db.select(Treasure)).scalars().all()}
    # B: rain and night treasures that are not out right now stay hidden here too (conditions.py)
    from condition_api import hidden_ids  # here, not at the top (weather_api imports routing)
    user = current_user()
    hidden = hidden_ids(treasures.values(), user.id if user else None)
    treasures = {tid: t for tid, t in treasures.items() if tid not in hidden}
    ratings = rating_summaries()

    best = top_rated([{"id": tid, "stars_sum": r["stars_sum"], "count": r["count"]}
                      for tid, r in ratings.items() if tid in treasures])

    now = datetime.now(timezone.utc)
    since = now - timedelta(days=TRENDING_DAYS)
    events = {}
    finds = db.session.execute(db.select(CoinTransaction.treasure_id, CoinTransaction.created_at).where(
        CoinTransaction.reason == FOUND_REASON, CoinTransaction.treasure_id.is_not(None),
        CoinTransaction.created_at >= since.replace(tzinfo=None))).all()
    rated = db.session.execute(db.select(TreasureRating.treasure_id, TreasureRating.updated_at).where(
        TreasureRating.updated_at >= since.replace(tzinfo=None))).all()
    finds_this_week = {}
    for tid, moment in finds:
        events.setdefault(tid, []).append(moment)
        finds_this_week[tid] = finds_this_week.get(tid, 0) + 1
    for tid, moment in rated:
        events.setdefault(tid, []).append(moment)
    hot = trending({tid: times for tid, times in events.items() if tid in treasures}, now)

    from coin_api import current_values  # here, not at the top: coin_api is imported by many files
    values = current_values(treasures.values(), now)

    def item(tid):
        r = ratings.get(tid, {"average": None, "count": 0})
        return {**treasures[tid].to_dict(), "rating": {"average": r["average"], "count": r["count"]},
                "finds_this_week": finds_this_week.get(tid, 0),
                "value": values[tid]}  # what a find pays right now (treasure_value.py)

    fresh = newest_unrated(treasures, ratings)
    from ratings import home_lists  # B: what the welcome page shows, without repeats
    home_top, home_hot = home_lists(best, fresh, hot)
    return jsonify(top_rated=[item(t) for t in best], trending=[item(t) for t in hot],
                   new=[item(t) for t in fresh],
                   home={"top": [item(t) for t in home_top], "trending": [item(t) for t in home_hot]})

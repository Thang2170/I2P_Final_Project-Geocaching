"""The first-time tour for new players (owner: B). Rules and words live in onboarding.py.

Like route_api.py, this lives in its own Blueprint.
The map page asks GET /api/onboarding when it opens; if "show" is true it plays the tour.
When the player finishes or skips it, the page sends POST /api/onboarding/seen.
"""

from flask import Blueprint, jsonify, request
from sqlalchemy.exc import IntegrityError

from auth_api import current_user
from coin_api import FOUND_REASON
from models import (CoinTransaction, HuntMember, Journey, Post, Profile, Purchase, TourSeen, Treasure,
                    db)
from onboarding import TOUR_STEPS, parse_ending, quest_list, should_show

onboarding_api = Blueprint("onboarding_api", __name__)


def _has(query):
    return db.session.execute(query.limit(1)).first() is not None


def _quests_done(user):
    """Which of the first quests this player has done, worked out from what is saved."""
    uid = user.id
    profile = db.session.get(Profile, uid)
    checks = {
        "weight": profile is not None and profile.weight_kg is not None,
        "find": _has(db.select(CoinTransaction.id).where(CoinTransaction.user_id == uid,
                                                          CoinTransaction.reason == FOUND_REASON))
                or _has(db.select(Journey.id).where(Journey.user_id == uid)),
        "hide": _has(db.select(Treasure.id).where(Treasure.created_by == uid)),
        "post": _has(db.select(Post.id).where(Post.user_id == uid, Post.journey_id.is_(None))),
        "join": _has(db.select(HuntMember.id).where(HuntMember.user_id == uid)),
        "buy": _has(db.select(Purchase.id).where(Purchase.user_id == uid)),
    }
    return {qid for qid, done in checks.items() if done}


@onboarding_api.route("/api/onboarding")
def onboarding():
    """The tour and the first-quests checklist. ?again=1 shows the tour even if it was seen."""
    user = current_user()
    if user is None:
        return jsonify(error="Log in first"), 401
    seen = db.session.get(TourSeen, user.id) is not None
    return jsonify(
        show=should_show(seen, asked_again=request.args.get("again") == "1"),
        username=user.username,
        steps=list(TOUR_STEPS),
        quests=quest_list(_quests_done(user)))


@onboarding_api.route("/api/onboarding/seen", methods=["POST"])
def tour_seen():
    """Remember that the player finished or skipped the tour. Send JSON: how."""
    user = current_user()
    if user is None:
        return jsonify(error="Log in first"), 401
    try:
        how = parse_ending(request.get_json(silent=True))
    except ValueError as err:
        return jsonify(error=str(err)), 400

    record = db.session.get(TourSeen, user.id)
    if record is None:
        db.session.add(TourSeen(user_id=user.id, how=how))
    else:
        record.how = how  # watched again: keep the latest
    try:
        db.session.commit()
    except IntegrityError:  # two tabs at once: the other one saved it
        db.session.rollback()
    return jsonify(ok=True, how=how)

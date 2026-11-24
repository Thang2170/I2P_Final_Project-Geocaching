"""Daily streaks and weekly challenges (owner: B). Rules live in streaks.py.

- GET  /api/challenges                 your streak and this week's challenges
- POST /api/challenges/<id>/claim      get the coins for a finished challenge
The numbers come from what the app already saves: finds (coin_transactions) and finished
hunts (journeys). Only claims need a table of their own (challenge_claims).
"""

from datetime import datetime, timedelta, timezone

from flask import Blueprint, jsonify
from sqlalchemy.exc import IntegrityError

from auth_api import current_user
from models import ChallengeClaim, CoinTransaction, Journey, db
from streaks import (CHALLENGE_REWARD, challenge_list, claim_problem, local_day, streaks, week_numbers,
                     week_start)

challenge_api = Blueprint("challenge_api", __name__)

CLAIM_REASON = "weekly_challenge"


def _now():
    return datetime.now(timezone.utc)


def _activity(user_id):
    """(finds as (when, coins), hunts as (when, metres)) for this player."""
    from coin_api import FOUND_REASON  # here, not at the top: coin_api imports many files
    finds = db.session.execute(db.select(CoinTransaction.created_at, CoinTransaction.amount).where(
        CoinTransaction.user_id == user_id, CoinTransaction.reason == FOUND_REASON)).all()
    hunts = db.session.execute(db.select(Journey.created_at, Journey.distance_m).where(
        Journey.user_id == user_id)).all()
    return [tuple(r) for r in finds], [tuple(r) for r in hunts]


def _claimed(user_id, monday):
    return set(db.session.execute(db.select(ChallengeClaim.challenge_id).where(
        ChallengeClaim.user_id == user_id, ChallengeClaim.week_start == monday)).scalars())


def _state(user):
    now = _now()
    today = local_day(now)
    monday = week_start(today)
    finds, hunts = _activity(user.id)
    days = {local_day(w) for w, _ in finds} | {local_day(w) for w, _ in hunts}
    current, best = streaks(days, today)
    numbers = week_numbers(finds, hunts, monday)
    return monday, numbers, {
        "streak": {"current": current, "best": best, "today_done": today in days},
        "week": {"start": monday.isoformat(), "end": (monday + timedelta(days=6)).isoformat()},
        "challenges": challenge_list(numbers, _claimed(user.id, monday)),
    }


@challenge_api.route("/api/challenges")
def my_challenges():
    user = current_user()
    if user is None:
        return jsonify(error="Log in first"), 401
    return jsonify(_state(user)[2])


@challenge_api.route("/api/challenges/<challenge_id>/claim", methods=["POST"])
def claim(challenge_id):
    user = current_user()
    if user is None:
        return jsonify(error="Log in first"), 401
    monday, numbers, _ = _state(user)
    problem = claim_problem(challenge_id, numbers, _claimed(user.id, monday))
    if problem:
        return jsonify(error=problem), 404 if problem == "No such challenge" else 400
    db.session.add(ChallengeClaim(user_id=user.id, week_start=monday, challenge_id=challenge_id))
    db.session.add(CoinTransaction(user_id=user.id, amount=CHALLENGE_REWARD, reason=CLAIM_REASON))
    try:
        db.session.commit()
    except IntegrityError:  # a double tap: the other one was paid
        db.session.rollback()
        return jsonify(error="You already claimed this one this week"), 400
    from coin_api import get_balance
    return jsonify(challenge=challenge_id, coins_earned=CHALLENGE_REWARD, balance=get_balance(user.id),
                   **_state(user)[2])

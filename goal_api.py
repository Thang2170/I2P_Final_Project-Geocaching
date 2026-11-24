"""Health goals and milestones (owner: B). Rules live in goals.py.

- GET  /api/goal                          your goal, this week's milestones and the week strip
- GET  /api/goal/choices                  the three goals you can pick
- POST /api/goal          {goal}          pick or change your goal: steps, active or rehab
- POST /api/goal/milestones/<id>/claim    collect a finished milestone's coins
"""

from datetime import datetime, timedelta, timezone

from flask import Blueprint, jsonify, request
from sqlalchemy.exc import IntegrityError

from auth_api import current_user
from goals import (GOAL_TEXT, GOALS, daily_numbers, find_milestone, milestones, parse_goal, rehab_advice,
                   week_strip)
from health import max_heart_rate
from models import CoinTransaction, GoalChoice, GoalMilestone, Journey, db
from streaks import local_day, week_start
from walk_api import age_of

goal_api = Blueprint("goal_api", __name__)

CLAIM_REASON = "goal_milestone"
HISTORY_WEEKS = 26  # rehab looks back at most this far


def _today():
    return local_day(datetime.now(timezone.utc))


def _days(user_id, since):
    """Daily numbers from the band and the hunts, from the Monday of `since` on."""
    from health_api import HealthReading  # here, not at the top: health_api imports walk_api
    start = datetime.combine(week_start(since), datetime.min.time()) - timedelta(hours=8)  # Taiwan midnight in UTC
    band = db.session.execute(db.select(HealthReading.at, HealthReading.hr, HealthReading.steps).where(
        HealthReading.user_id == user_id, HealthReading.at >= start)).all()
    hunts = db.session.execute(db.select(Journey.created_at, Journey.duration_s, Journey.steps).where(
        Journey.user_id == user_id, Journey.created_at >= start)).all()
    return daily_numbers([tuple(r) for r in band], [tuple(r) for r in hunts], max_heart_rate(age_of(user_id)))


def _collected(user_id, items):
    starts = {m["period_start"] for m in items}
    rows = db.session.execute(db.select(GoalMilestone.milestone_id, GoalMilestone.period_start).where(
        GoalMilestone.user_id == user_id, GoalMilestone.period_start.in_(starts))).all()
    return {(mid, start) for mid, start in rows}


def _state(user):
    choice = db.session.get(GoalChoice, user.id)
    if choice is None:
        return None, {"goal": None, "choices": _choices()}
    today = _today()
    since = max(choice.started_on, today - timedelta(weeks=HISTORY_WEEKS))
    days = _days(user.id, min(since, week_start(today)))
    items = milestones(choice.goal, days, today, choice.started_on)
    got = _collected(user.id, items)
    for m in items:
        m["claimed"] = (m["id"], m["period_start"]) in got
        m["period_start"] = m["period_start"].isoformat()
    advice = rehab_advice(days, today, max_heart_rate(age_of(user.id))) if choice.goal == "rehab" else None
    return (choice, days, today), {
        "goal": choice.goal, "title": GOALS[choice.goal], "text": GOAL_TEXT[choice.goal],
        "started_on": choice.started_on.isoformat(), "milestones": items,
        "week": week_strip(choice.goal, days, today, choice.started_on), "advice": advice,
    }


@goal_api.route("/api/goal")
def my_goal():
    user = current_user()
    if user is None:
        return jsonify(error="Log in first"), 401
    return jsonify(_state(user)[1])


def _choices():
    return [{"id": k, "title": v, "text": GOAL_TEXT[k]} for k, v in GOALS.items()]


@goal_api.route("/api/goal/choices")
def choices():
    return jsonify(choices=_choices())


@goal_api.route("/api/goal", methods=["POST"])
def pick_goal():
    user = current_user()
    if user is None:
        return jsonify(error="Log in first"), 401
    data = request.get_json(silent=True) or {}
    try:
        goal = parse_goal(data.get("goal") if isinstance(data, dict) else None)
    except ValueError as err:
        return jsonify(error=str(err)), 400
    choice = db.session.get(GoalChoice, user.id)
    if choice is None:
        db.session.add(GoalChoice(user_id=user.id, goal=goal, started_on=_today()))
    elif choice.goal != goal:  # a new goal starts again (rehab from 10 minutes)
        choice.goal, choice.started_on = goal, _today()
    db.session.commit()
    return jsonify(_state(user)[1])


@goal_api.route("/api/goal/milestones/<milestone_id>/claim", methods=["POST"])
def claim(milestone_id):
    user = current_user()
    if user is None:
        return jsonify(error="Log in first"), 401
    found, _ = _state(user)
    if found is None:
        return jsonify(error="Pick a goal first"), 400
    choice, days, today = found
    m = find_milestone(choice.goal, days, today, choice.started_on, milestone_id)
    if m is None:
        return jsonify(error="No such milestone for your goal"), 404
    if not m["done"]:
        return jsonify(error=f"Not yet: {m['progress']} of {m['target']} {m['unit']}"), 400
    db.session.add(GoalMilestone(user_id=user.id, milestone_id=milestone_id, period_start=m["period_start"],
                                 coins=m["reward"]))
    db.session.add(CoinTransaction(user_id=user.id, amount=m["reward"], reason=CLAIM_REASON))
    try:
        db.session.commit()
    except IntegrityError:  # already collected (or a double tap)
        db.session.rollback()
        return jsonify(error="You already collected this one"), 400
    from coin_api import get_balance
    return jsonify(_state(user)[1] | {"coins_earned": m["reward"], "balance": get_balance(user.id)})

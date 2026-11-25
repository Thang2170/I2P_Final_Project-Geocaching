"""Daily habits: the goal ring, streak freezes and sharing your streak (owner: B). Rules: habits.py.

- GET  /api/habits           today's ring, your streak (freezes included) and your freezes
- POST /api/habits/freeze    buy a streak freeze (FREEZE_PRICE coins)
- POST /api/habits/share     post your streak to the Community (once a day)
The streak on the "This week" card (challenge_api.py) is worked out here too, so both agree.
"""

from datetime import datetime, timedelta, timezone

from flask import Blueprint, jsonify
from sqlalchemy.exc import IntegrityError

from auth_api import current_user
from habits import (FREEZE_PRICE, LOOKBACK_DAYS, MAX_FREEZES, REMIND_FROM_HOUR, freeze_problem, freezes_to_use,
                    ring, ring_days, share_text, streak_at_risk)
from models import CoinTransaction, GoalChoice, Notification, Post, StreakFreeze, StreakReminder, StreakShare, db
from streaks import local_day, streaks

habit_api = Blueprint("habit_api", __name__)

FREEZE_REASON = "streak_freeze"


def _today():
    return local_day(datetime.now(timezone.utc))


def _freezes(user_id):
    return db.session.execute(db.select(StreakFreeze).where(StreakFreeze.user_id == user_id)
                              .order_by(StreakFreeze.id)).scalars().all()


def streak_info(user, today=None):
    """Your streak with closed rings and freezes counted. Uses up freezes for a fresh gap.

    Returns {"current", "best", "today_done", "frozen_days", "ring", "freezes"}.
    """
    from challenge_api import _activity  # here, not at the top: challenge_api imports this file
    from goal_api import _days
    today = today or _today()
    choice = db.session.get(GoalChoice, user.id)
    goal = choice.goal if choice else None
    started_on = choice.started_on if choice else today
    days = _days(user.id, today - timedelta(days=LOOKBACK_DAYS))
    finds, hunts = _activity(user.id)
    active = {local_day(w) for w, _ in finds} | {local_day(w) for w, _ in hunts} \
        | ring_days(goal, days, today, started_on)

    freezes = _freezes(user.id)
    frozen = {f.used_on for f in freezes if f.used_on}
    unused = [f for f in freezes if f.used_on is None]
    use = freezes_to_use(active, frozen, today, [f.bought_on for f in unused])
    for missed in use:  # cover each missed day with the oldest freeze bought before it
        freeze = next(f for f in unused if f.bought_on < missed and f.used_on is None)
        freeze.used_on = missed
        frozen.add(missed)
    if use:
        try:
            db.session.commit()
        except IntegrityError:  # another request used them at the same moment
            db.session.rollback()
            return streak_info(user, today)

    current, best = streaks(active | frozen, today)
    today_ring = ring(goal, days, today, started_on)
    return {
        "current": current, "best": best, "today_done": today in active,
        "frozen_days": sorted(d.isoformat() for d in frozen if today - d <= timedelta(days=current)),
        "used_freeze_now": [d.isoformat() for d in use],
        "ring": today_ring,
        "freezes": {"owned": sum(1 for f in freezes if f.used_on is None), "max": MAX_FREEZES,
                    "price": FREEZE_PRICE},
    }


def _state(user):
    today = _today()
    info = streak_info(user, today)
    shared = db.session.execute(db.select(StreakShare.post_id).where(
        StreakShare.user_id == user.id, StreakShare.day == today)).scalar()
    return info | {"shared_today": shared is not None, "shared_post_id": shared}


@habit_api.route("/api/habits")
def my_habits():
    user = current_user()
    if user is None:
        return jsonify(error="Log in first"), 401
    return jsonify(_state(user))


@habit_api.route("/api/habits/freeze", methods=["POST"])
def buy_freeze():
    user = current_user()
    if user is None:
        return jsonify(error="Log in first"), 401
    from coin_api import get_balance
    owned = db.session.execute(db.select(db.func.count()).select_from(StreakFreeze).where(
        StreakFreeze.user_id == user.id, StreakFreeze.used_on.is_(None))).scalar()
    problem = freeze_problem(owned, get_balance(user.id))
    if problem:
        return jsonify(error=problem), 400
    db.session.add(StreakFreeze(user_id=user.id, bought_on=_today()))
    db.session.add(CoinTransaction(user_id=user.id, amount=-FREEZE_PRICE, reason=FREEZE_REASON))
    db.session.commit()
    return jsonify(_state(user) | {"balance": get_balance(user.id)})


@habit_api.route("/api/habits/share", methods=["POST"])
def share_streak():
    user = current_user()
    if user is None:
        return jsonify(error="Log in first"), 401
    from feed_api import _last, too_soon  # the Community's own anti-spam wait
    today = _today()
    info = streak_info(user, today)
    try:
        text = share_text(info["current"], info["best"], info["ring"]["closed"])
    except ValueError as err:
        return jsonify(error=str(err)), 400
    if db.session.execute(db.select(StreakShare.post_id).where(
            StreakShare.user_id == user.id, StreakShare.day == today)).first():
        return jsonify(error="You already shared your streak today."), 400
    wait = too_soon("post", _last(Post, user.id, Post.journey_id.is_(None)))
    if wait:
        return wait
    post = Post(user_id=user.id, text=text)
    db.session.add(post)
    db.session.flush()
    db.session.add(StreakShare(post_id=post.id, user_id=user.id, day=today, streak=info["current"]))
    try:
        db.session.commit()
    except IntegrityError:  # a double tap
        db.session.rollback()
        return jsonify(error="You already shared your streak today."), 400
    return jsonify(_state(user) | {"post_id": post.id, "text": text}), 201


# ---------------------------------------------------------------- the evening "streak at risk" reminder

def _local_now():
    return datetime.now(timezone.utc) + timedelta(hours=8)  # Taiwan time


def remind_if_at_risk(user):
    """From 8 p.m., once a day: if your streak would end at midnight, tell the bell.

    Called when the bell asks for notifications (every 30 s while the app is open), so no
    background job is needed. The first check after 8 p.m. is saved, so it runs once a day.
    """
    from notify_rules import STREAK_RISK  # here, not at the top: notify_api imports this file
    local = _local_now()
    if local.hour < REMIND_FROM_HOUR:
        return None
    today = local.date()
    if db.session.execute(db.select(StreakReminder.id).where(
            StreakReminder.user_id == user.id, StreakReminder.day == today)).first():
        return None
    info = streak_info(user, today)
    owned = info["freezes"]["owned"]
    reminder = StreakReminder(user_id=user.id, day=today, streak=info["current"], freezes=owned)
    if streak_at_risk(info["current"], info["today_done"], local.hour):
        note = Notification(user_id=user.id, kind=STREAK_RISK)
        db.session.add(note)
        db.session.flush()
        reminder.notification_id = note.id
    db.session.add(reminder)
    try:
        db.session.commit()
    except IntegrityError:  # two bells asked at the same moment
        db.session.rollback()
        return None
    return reminder

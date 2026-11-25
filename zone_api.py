"""Heart-rate zone on the map: live zone, bonus coins, warnings, cool-down quest. Owner: B.

Thin: the rules are in zone_coach.py. Readings come from the band (health_api.py, A's).
"""

from datetime import datetime, timedelta, timezone

from flask import Blueprint, jsonify, request
from sqlalchemy.exc import IntegrityError

from auth_api import current_user
from health import max_heart_rate
from models import CoinTransaction, CooldownDone, Journey, ZoneBonus, db
from walk_api import age_of
from walk_input import parse_duration_s
from zone_coach import (HARD_LIMIT_S, COOLDOWN_REWARD, COOLDOWN_S, COOLDOWN_WINDOW_S, bonus_coins, bonus_seconds,
                        cooldown_bpm, cooldown_progress, now_report, warning)

zone_api = Blueprint("zone_api", __name__)

BONUS_REASON = "zone_bonus"
COOLDOWN_REASON = "cooldown_quest"


def _naive(when):
    """SQLite keeps times without a time zone (they are UTC)."""
    return when.astimezone(timezone.utc).replace(tzinfo=None) if when.tzinfo else when


def readings_between(user_id, start, end):
    """(time, heart rate) pairs from the band, oldest first."""
    from health_api import HealthReading  # here, not at the top: health_api imports walk_api
    rows = db.session.execute(
        db.select(HealthReading.at, HealthReading.hr)
        .where(HealthReading.user_id == user_id, HealthReading.hr.is_not(None),
               HealthReading.at >= _naive(start), HealthReading.at <= _naive(end))
        .order_by(HealthReading.at)).all()
    return [(at, hr) for at, hr in rows]


def hr_max_of(user_id):
    return max_heart_rate(age_of(user_id))


def pay_zone_bonus(user, journey):
    """Called once a hunt is saved: coins for the time spent in the 60-80% zone."""
    end = journey.created_at
    readings = readings_between(user.id, end - timedelta(seconds=journey.duration_s), end)
    seconds = bonus_seconds(readings, hr_max_of(user.id))
    coins = bonus_coins(seconds)
    db.session.add(ZoneBonus(journey_id=journey.id, user_id=user.id, seconds=seconds, coins=coins))
    if coins:
        db.session.add(CoinTransaction(user_id=user.id, amount=coins, reason=BONUS_REASON))
    try:
        db.session.commit()
    except IntegrityError:  # already paid
        db.session.rollback()
        return 0
    return coins


@zone_api.route("/api/zone/now")
def zone_now():
    """GET /api/zone/now?duration_s=600: your zone now, bonus so far and any warning."""
    user = current_user()
    if user is None:
        return jsonify(error="Log in first"), 401
    try:
        duration_s = parse_duration_s(request.args.get("duration_s"))
    except ValueError as err:
        return jsonify(error=str(err)), 400
    return jsonify(zone_report(user, duration_s))


WARN_LOOKBACK_S = HARD_LIMIT_S + 2 * 60  # the warnings look back at least 12 minutes


def zone_report(user, duration_s):
    """Your zone now, bonus so far and any warning (also used by /api/journey/live).

    The bonus counts this journey only (the last duration_s seconds). The "too hard for too
    long" warnings look back at least WARN_LOOKBACK_S, so they also count the minutes just
    before you started this journey: your heart doesn't reset when you press Start.
    """
    now = datetime.now(timezone.utc)
    hr_max = hr_max_of(user.id)
    readings = readings_between(user.id, now - timedelta(seconds=max(duration_s, WARN_LOOKBACK_S)), now)
    journey_start = _naive(now) - timedelta(seconds=duration_s)
    report = now_report([r for r in readings if r[0] >= journey_start], hr_max)
    if readings:
        report["warning"] = warning(readings, hr_max)
        if not report["has_band"]:  # band readings from before this journey only
            report = now_report(readings[-1:], hr_max) | {"bonus_seconds": 0, "bonus_coins": 0,
                                                          "zone_seconds": [0] * 5, "warning": report["warning"]}
    report["max_hr"] = hr_max
    return report


def _latest_journey(user):
    return db.session.execute(db.select(Journey).where(Journey.user_id == user.id)
                              .order_by(Journey.created_at.desc(), Journey.id.desc()).limit(1)).scalar()


@zone_api.route("/api/zone/cooldown", methods=["POST"])
def cooldown():
    """Check the cool-down quest of your latest saved hunt, and pay it once it is done.

    Safe to call again and again: it is paid only once per hunt.
    """
    user = current_user()
    if user is None:
        return jsonify(error="Log in first"), 401
    journey = _latest_journey(user)
    if journey is None:
        return jsonify(error="Finish a hunt first."), 404
    hr_max = hr_max_of(user.id)
    goal = dict(journey_id=journey.id, goal_s=COOLDOWN_S, below_bpm=cooldown_bpm(hr_max),
                reward=COOLDOWN_REWARD)
    if db.session.get(CooldownDone, journey.id):
        return jsonify(goal | dict(state="done", done_s=COOLDOWN_S, paid=0))

    start = _naive(journey.created_at)
    end = start + timedelta(seconds=COOLDOWN_WINDOW_S)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    readings = readings_between(user.id, start, min(now, end))
    done_s = cooldown_progress(readings, hr_max)
    if done_s >= COOLDOWN_S:
        db.session.add(CooldownDone(journey_id=journey.id, user_id=user.id))
        db.session.add(CoinTransaction(user_id=user.id, amount=COOLDOWN_REWARD, reason=COOLDOWN_REASON))
        try:
            db.session.commit()
        except IntegrityError:  # a second tab got there first
            db.session.rollback()
            return jsonify(goal | dict(state="done", done_s=COOLDOWN_S, paid=0))
        return jsonify(goal | dict(state="done", done_s=COOLDOWN_S, paid=COOLDOWN_REWARD))
    if now > end:
        return jsonify(goal | dict(state="missed", done_s=done_s, paid=0))
    return jsonify(goal | dict(state="no_band" if not readings else "going", done_s=done_s, paid=0))

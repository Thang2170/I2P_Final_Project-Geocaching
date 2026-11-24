"""Safety alerts during a hunt (owner: B). Rules live in safety.py.

- GET /api/safety/now      the band's last 2 minutes: ok, caution, or stop (the map stops the hunt)
- GET /api/safety/alerts   your recent stops
"""

from datetime import datetime, timedelta, timezone

from flask import Blueprint, jsonify

from auth_api import current_user
from health import max_heart_rate
from models import SafetyAlert, db
from safety import check
from walk_api import age_of

safety_api = Blueprint("safety_api", __name__)

WINDOW_S = 120            # look at the last 2 minutes of readings
SAME_ALERT_S = 10 * 60    # the same alert is saved once per 10 minutes


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)  # SQLite keeps UTC without a zone


def recent_readings(user_id, now):
    from health_api import HealthReading  # here, not at the top: health_api imports walk_api
    rows = db.session.execute(
        db.select(HealthReading.at, HealthReading.hr, HealthReading.spo2)
        .where(HealthReading.user_id == user_id, HealthReading.at >= now - timedelta(seconds=WINDOW_S),
               HealthReading.at <= now)
        .order_by(HealthReading.at)).all()
    return [tuple(r) for r in rows]


def _remember(user, result, now):
    """Save a stop, unless the same one was saved in the last 10 minutes."""
    recent = db.session.execute(db.select(SafetyAlert.id).where(
        SafetyAlert.user_id == user.id, SafetyAlert.reason == result["reason"],
        SafetyAlert.created_at >= now - timedelta(seconds=SAME_ALERT_S))).first()
    if recent is None:
        db.session.add(SafetyAlert(user_id=user.id, reason=result["reason"], title=result["title"][:80]))
        db.session.commit()


@safety_api.route("/api/safety/now")
def safety_now():
    user = current_user()
    if user is None:
        return jsonify(error="Log in first"), 401
    now = _now()
    readings = recent_readings(user.id, now)
    result = check(readings, max_heart_rate(age_of(user.id)))
    if result["level"] == "stop":
        _remember(user, result, now)
    return jsonify(result | {"has_band": bool(readings)})


@safety_api.route("/api/safety/alerts")
def my_alerts():
    user = current_user()
    if user is None:
        return jsonify(error="Log in first"), 401
    rows = db.session.execute(db.select(SafetyAlert).where(SafetyAlert.user_id == user.id)
                              .order_by(SafetyAlert.created_at.desc()).limit(20)).scalars()
    return jsonify(alerts=[{"reason": a.reason, "title": a.title,
                            "at": a.created_at.replace(tzinfo=timezone.utc).isoformat()} for a in rows])

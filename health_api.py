"""The wearable's endpoints and the Health page (owner: A).

Rules: health.py. Local AI: health_ai.py. Device code: esp32/.

    GET    /health                          the page
    POST   /api/health/devices   {"name"}    pair a device: answers its secret token ONCE
    GET    /api/health/devices              your devices (never the tokens)
    DELETE /api/health/devices/<id>
    POST   /api/health/readings             the ESP32 uploads; header "Authorization: Bearer <token>"
    GET    /api/health/summary              your last walk: numbers, chart, advice
    POST   /api/health/analyse              the local AI's coach summary of your last walk
    POST   /api/health/profile   {"age"}

Tokens are stored as SHA-256 hashes, like passwords: a stolen database can't upload as you.
"""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from flask import Blueprint, jsonify, redirect, render_template, request, url_for

from auth_api import current_user
from health import (DEFAULT_AGE, as_utc, heart_chart_points, parse_batch, rules_advice, split_walks,
                    summarize)
from health_ai import analyse
from models import db

health_api = Blueprint("health_api", __name__)

MAX_DEVICES = 5


class HealthDevice(db.Model):
    __tablename__ = "health_devices"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    name = db.Column(db.String(40), nullable=False)
    token_hash = db.Column(db.String(64), nullable=False, unique=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    last_seen = db.Column(db.DateTime, nullable=True)


class HealthReading(db.Model):
    __tablename__ = "health_readings"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    device_id = db.Column(db.Integer, db.ForeignKey("health_devices.id"), nullable=False)
    at = db.Column(db.DateTime, nullable=False, index=True)
    hr = db.Column(db.Integer, nullable=True)
    spo2 = db.Column(db.Float, nullable=True)
    steps = db.Column(db.Integer, nullable=False, default=0)
    temp_c = db.Column(db.Float, nullable=True)


class HealthProfile(db.Model):
    __tablename__ = "health_profiles"
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), primary_key=True)
    age = db.Column(db.Integer, nullable=False, default=DEFAULT_AGE)
    resting_hr = db.Column(db.Integer, nullable=True)  # the player's own, if they know it


def hash_token(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _login_or_error():
    user = current_user()
    return (user, None) if user else (None, (jsonify(error="Log in first"), 401))


def _age(user_id):
    profile = db.session.get(HealthProfile, user_id)
    return profile.age if profile else DEFAULT_AGE


def _resting(user_id):
    profile = db.session.get(HealthProfile, user_id)
    return profile.resting_hr if profile else None


def _weight(user):
    from walk_api import _saved_weight  # B's saved weight (Account page), else the default
    from walk_input import DEFAULT_WEIGHT_KG
    return _saved_weight(user) or DEFAULT_WEIGHT_KG


def last_walk(user_id):
    """The readings of the newest walk, oldest first (only the last 2 days are looked at)."""
    since = datetime.now(timezone.utc) - timedelta(days=2)
    rows = db.session.execute(
        db.select(HealthReading).where(HealthReading.user_id == user_id, HealthReading.at >= since)
        .order_by(HealthReading.at)).scalars().all()
    readings = [{"at": r.at, "hr": r.hr, "spo2": r.spo2, "steps": r.steps} for r in rows]
    walks = split_walks(readings)
    return walks[-1] if walks else None


# ------------------------------------------------------------ page


@health_api.route("/health")
def health_page():
    if current_user() is None:
        return redirect(url_for("auth_api.login_page", next="/health"))
    return render_template("health.html")


# ------------------------------------------------------------ devices


@health_api.route("/api/health/devices", methods=["POST"])
def pair_device():
    user, error = _login_or_error()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    name = str(data.get("name") or "My StepQuest band").strip()[:40] or "My StepQuest band"
    count = db.session.execute(db.select(db.func.count()).select_from(HealthDevice)
                               .where(HealthDevice.user_id == user.id)).scalar_one()
    if count >= MAX_DEVICES:
        return jsonify(error=f"At most {MAX_DEVICES} devices. Remove an old one first."), 409
    token = secrets.token_urlsafe(24)
    device = HealthDevice(user_id=user.id, name=name, token_hash=hash_token(token))
    db.session.add(device)
    db.session.commit()
    # The only time the token is shown: put it in esp32/config.py
    return jsonify(id=device.id, name=device.name, token=token), 201


@health_api.route("/api/health/devices", methods=["GET"])
def list_devices():
    user, error = _login_or_error()
    if error:
        return error
    rows = db.session.execute(db.select(HealthDevice).where(HealthDevice.user_id == user.id)
                              .order_by(HealthDevice.id)).scalars().all()
    return jsonify(devices=[{"id": d.id, "name": d.name,
                             "last_seen": as_utc(d.last_seen).isoformat() if d.last_seen else None}
                            for d in rows])


@health_api.route("/api/health/devices/<int:device_id>", methods=["DELETE"])
def remove_device(device_id):
    user, error = _login_or_error()
    if error:
        return error
    device = db.session.get(HealthDevice, device_id)
    if device is None or device.user_id != user.id:
        return jsonify(error="No such device"), 404
    db.session.execute(db.delete(HealthReading).where(HealthReading.device_id == device.id))
    db.session.delete(device)
    db.session.commit()
    return jsonify(ok=True)


# ------------------------------------------------------------ the device uploads


@health_api.route("/api/health/readings", methods=["POST"])
def upload_readings():
    """The ESP32 sends its readings here (no login cookie: it proves itself with its token)."""
    header = request.headers.get("Authorization", "")
    token = header[7:].strip() if header.startswith("Bearer ") else ""
    device = db.session.execute(db.select(HealthDevice).where(
        HealthDevice.token_hash == hash_token(token))).scalar_one_or_none() if token else None
    if device is None:
        return jsonify(error="Unknown device: pair it on the Health page and copy its token"), 401
    try:
        readings = parse_batch(request.get_json(silent=True))
    except ValueError as err:
        return jsonify(error=str(err)), 400
    now = datetime.now(timezone.utc)
    for r in readings:
        db.session.add(HealthReading(user_id=device.user_id, device_id=device.id,
                                     at=now - timedelta(seconds=r["age_s"]), hr=r["hr"], spo2=r["spo2"],
                                     steps=r["steps"] or 0, temp_c=r["temp_c"]))
    device.last_seen = now
    db.session.commit()
    return jsonify(saved=len(readings)), 201


# ------------------------------------------------------------ results


@health_api.route("/api/health/summary")
def summary():
    user, error = _login_or_error()
    if error:
        return error
    walk = last_walk(user.id)
    if walk is None:
        return jsonify(walk=None, age=_age(user.id), resting_hr=_resting(user.id))
    s = summarize(walk, age=_age(user.id), weight_kg=_weight(user), resting_hr=_resting(user.id))
    return jsonify(walk=s, advice=rules_advice(s), chart=heart_chart_points(walk), age=_age(user.id),
                   resting_hr=_resting(user.id))


@health_api.route("/api/health/analyse", methods=["POST"])
def analyse_last_walk():
    user, error = _login_or_error()
    if error:
        return error
    walk = last_walk(user.id)
    if walk is None:
        return jsonify(error="No walk yet: wear the sensor on a walk first."), 404
    return jsonify(analyse(summarize(walk, age=_age(user.id), weight_kg=_weight(user),
                                     resting_hr=_resting(user.id))))


@health_api.route("/api/health/profile", methods=["POST"])
def save_profile():
    user, error = _login_or_error()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    try:
        age = int(data.get("age"))
    except (TypeError, ValueError):
        return jsonify(error="age must be a whole number"), 400
    if not 8 <= age <= 100:
        return jsonify(error="age must be between 8 and 100"), 400
    resting = data.get("resting_hr")
    if resting in (None, ""):
        resting = None
    else:
        try:
            resting = int(resting)
        except (TypeError, ValueError):
            return jsonify(error="resting heart rate must be a whole number"), 400
        if not 30 <= resting <= 120:
            return jsonify(error="resting heart rate must be between 30 and 120"), 400
    profile = db.session.get(HealthProfile, user.id) or HealthProfile(user_id=user.id)
    profile.age, profile.resting_hr = age, resting
    db.session.add(profile)
    db.session.commit()
    return jsonify(age=age, resting_hr=resting)

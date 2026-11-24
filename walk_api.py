"""Steps and calories for a walk (owner: B, formulas by C in calculator.py).

The map sends the length of a route; Python does the maths and sends the answer
back. Like route_api.py, this lives in its own Blueprint.
"""

from datetime import datetime, timedelta, timezone

from flask import Blueprint, jsonify, request

from auth_api import current_user
from energy import walk_energy
from models import Profile, db
from walk_input import DEFAULT_WEIGHT_KG, parse_distance_m, parse_duration_s, parse_weight_kg

walk_api = Blueprint("walk_api", __name__)


def _saved_weight(user):
    """The weight this player saved, or None."""
    if user is None:
        return None
    profile = db.session.get(Profile, user.id)
    return profile.weight_kg if profile else None


def band_readings(user_id, duration_s, ended_at=None):
    """The band's readings during the last duration_s seconds (empty without a band)."""
    if user_id is None or not duration_s:
        return []
    from health_api import HealthReading  # here, not at the top: health_api imports this file
    end = ended_at or datetime.now(timezone.utc)
    start = end - timedelta(seconds=duration_s)
    rows = db.session.execute(db.select(HealthReading.hr, HealthReading.steps).where(
        HealthReading.user_id == user_id,
        HealthReading.at >= start.replace(tzinfo=None), HealthReading.at <= end.replace(tzinfo=None))).all()
    return [{"hr": hr, "steps": steps} for hr, steps in rows]


def age_of(user_id):
    from health_api import DEFAULT_AGE, HealthProfile  # (same reason)
    profile = db.session.get(HealthProfile, user_id) if user_id else None
    return profile.age if profile else DEFAULT_AGE


def energy_for(user, distance_m, weight_kg, duration_s=None, ended_at=None):
    """Steps and calories with the best formula we have data for (energy.py)."""
    user_id = user.id if user else None
    return walk_energy(distance_m, weight_kg, age_of(user_id), duration_s,
                       band_readings(user_id, duration_s, ended_at))


@walk_api.route("/api/walk-stats")
def walk_stats():
    """GET /api/walk-stats?distance_m=750[&weight_kg=60][&duration_s=600]

    Weight comes from the request, else from the logged-in player's saved
    weight, else from DEFAULT_WEIGHT_KG. weight_source says which one was used.
    B: with duration_s (a journey in progress) the calories use your speed, or your band's
    heart rate if it was on; "source" says which formula was used (energy.py).
    """
    try:
        distance_m = parse_distance_m(request.args.get("distance_m"))
        duration_s = None
        if "duration_s" in request.args:
            duration_s = parse_duration_s(request.args["duration_s"])
        weight_kg, source = None, None
        if "weight_kg" in request.args:
            weight_kg, source = parse_weight_kg(request.args["weight_kg"]), "request"
    except ValueError as err:
        return jsonify(error=str(err)), 400

    user = current_user()
    if weight_kg is None:
        weight_kg = _saved_weight(user)
        source = "profile"
        if weight_kg is None:
            weight_kg, source = DEFAULT_WEIGHT_KG, "default"

    energy = energy_for(user, distance_m, weight_kg, duration_s)
    return jsonify(
        distance_m=distance_m,
        steps=energy["steps"],
        calories=energy["calories"],
        source=energy["source"],
        source_text=energy["source_text"],
        weight_kg=weight_kg,
        weight_source=source,
    )


@walk_api.route("/api/me/weight", methods=["GET"])
def get_weight():
    user = current_user()
    if user is None:
        return jsonify(error="Log in first"), 401
    return jsonify(weight_kg=_saved_weight(user), default_kg=DEFAULT_WEIGHT_KG)


@walk_api.route("/api/me/weight", methods=["POST"])
def save_weight():
    """Save the logged-in player's weight. Send JSON or form field: weight_kg."""
    user = current_user()
    if user is None:
        return jsonify(error="Log in first"), 401

    data = request.get_json(silent=True)
    if data is None:
        data = request.form.to_dict()
    try:
        weight_kg = parse_weight_kg(data.get("weight_kg") if isinstance(data, dict) else None)
    except ValueError as err:
        return jsonify(error=str(err)), 400

    profile = db.session.get(Profile, user.id)
    if profile is None:
        profile = Profile(user_id=user.id)
        db.session.add(profile)
    profile.weight_kg = weight_kg
    db.session.commit()
    return jsonify(weight_kg=weight_kg)

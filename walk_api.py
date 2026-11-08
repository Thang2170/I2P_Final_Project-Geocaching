"""Steps and calories for a walk (owner: B, formulas by C in calculator.py).

The map sends the length of a route; Python does the maths and sends the answer
back. Like route_api.py, this lives in its own Blueprint.
"""

from flask import Blueprint, jsonify, request

from auth_api import current_user
from calculator import calories_from_distance, steps_from_distance
from models import Profile, db
from walk_input import DEFAULT_WEIGHT_KG, parse_distance_m, parse_weight_kg

walk_api = Blueprint("walk_api", __name__)


def _saved_weight(user):
    """The weight this player saved, or None."""
    if user is None:
        return None
    profile = db.session.get(Profile, user.id)
    return profile.weight_kg if profile else None


@walk_api.route("/api/walk-stats")
def walk_stats():
    """GET /api/walk-stats?distance_m=750[&weight_kg=60]

    Weight comes from the request, else from the logged-in player's saved
    weight, else from DEFAULT_WEIGHT_KG. weight_source says which one was used.
    """
    try:
        distance_m = parse_distance_m(request.args.get("distance_m"))
        weight_kg, source = None, None
        if "weight_kg" in request.args:
            weight_kg, source = parse_weight_kg(request.args["weight_kg"]), "request"
    except ValueError as err:
        return jsonify(error=str(err)), 400

    if weight_kg is None:
        weight_kg = _saved_weight(current_user())
        source = "profile"
        if weight_kg is None:
            weight_kg, source = DEFAULT_WEIGHT_KG, "default"

    return jsonify(
        distance_m=distance_m,
        steps=steps_from_distance(distance_m),
        calories=round(calories_from_distance(distance_m, weight_kg), 1),
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

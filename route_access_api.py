"""Step-free routes (owner: B). The rules live in route_access.py.

    GET  /api/me/route-access                    {"access": "walking" | "wheelchair", "choices": [...]}
    POST /api/me/route-access {"access": ...}    save your choice (the Account page)

route_api.py and trail_api.py call route_settings() to route each player their way.

app.py registers it like the other Blueprints:

    from route_access_api import route_access_api
    app.register_blueprint(route_access_api)
"""

from flask import Blueprint, jsonify, request

from auth_api import current_user
from models import RouteAccess, db
from route_access import CHOICES, LABELS, WALKING, ors_profile, parse_choice, route_extra

route_access_api = Blueprint("route_access_api", __name__)


def access_of(user):
    """This player's choice: walking unless they asked for step-free routes."""
    if user is None or getattr(user, "id", None) is None:
        return WALKING
    row = db.session.get(RouteAccess, user.id)
    return row.access if row else WALKING


def route_settings(user, weather_extra):
    """(choice, ORS profile, extra request settings) for this player and this weather."""
    choice = access_of(user)
    return choice, ors_profile(choice), route_extra(choice, weather_extra)


def _answer(choice):
    return jsonify(access=choice, choices=[{"id": c, "label": LABELS[c]} for c in CHOICES])


@route_access_api.route("/api/me/route-access", methods=["GET"])
def get_access():
    user = current_user()
    if user is None:
        return jsonify(error="Log in first"), 401
    return _answer(access_of(user))


@route_access_api.route("/api/me/route-access", methods=["POST"])
def set_access():
    user = current_user()
    if user is None:
        return jsonify(error="Log in first"), 401
    try:
        choice = parse_choice(request.get_json(silent=True))
    except ValueError as err:
        return jsonify(error=str(err)), 400
    row = db.session.get(RouteAccess, user.id)
    if choice == WALKING:
        if row is not None:
            db.session.delete(row)  # no row means walking
    elif row is None:
        db.session.add(RouteAccess(user_id=user.id, access=choice))
    else:
        row.access = choice
    db.session.commit()
    return _answer(choice)

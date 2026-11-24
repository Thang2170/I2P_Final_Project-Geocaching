"""Treasure Trail: POST /api/trail plans a walking loop for a step or time goal (owner: B).

The rules and the algorithm live in trail_planner.py. This file only reads the request,
picks the treasures you can still find, and asks routing.get_route (A's file, unchanged)
for the real walking path of the loop.
"""

from flask import Blueprint, jsonify, request

from auth_api import current_user
from calculator import steps_from_distance
from coin_api import found_treasure_ids
from models import Treasure, db
from routing import get_route
from trail_planner import parse_goal, plan_trail
from treasure_input import parse_number

trail_api = Blueprint("trail_api", __name__)


@trail_api.route("/api/trail", methods=["POST"])
def make_trail():
    """Send JSON: lat, lon (where you are) and steps OR minutes.

    Answers with the stops in walking order and the real walking path of the whole loop.
    """
    user = current_user()
    if user is None:
        return jsonify(error="Log in first"), 401
    data = request.get_json(silent=True) or {}
    try:
        lat = parse_number(data.get("lat"), "lat", -90, 90)
        lon = parse_number(data.get("lon"), "lon", -180, 180)
        budget_m, label = parse_goal(data)
    except ValueError as err:
        return jsonify(error=str(err)), 400

    # Only treasures you can still earn coins from: not found yet, and not your own.
    found = set(found_treasure_ids(user.id))
    treasures = [t for t in db.session.execute(db.select(Treasure)).scalars()
                 if t.id not in found and t.created_by != user.id]
    plan = plan_trail((lat, lon), [{"id": t.id, "lat": t.lat, "lon": t.lon} for t in treasures], budget_m)
    if not plan["ids"]:
        return jsonify(goal=label, stops=[], message=(
            "No treasure you haven't found fits in that walk. Try a longer one.")), 200

    by_id = {t.id: t for t in treasures}
    stops = [by_id[i] for i in plan["ids"]]
    route = get_route([(lat, lon), *[(t.lat, t.lon) for t in stops], (lat, lon)])
    return jsonify(
        goal=label,
        stops=[{"order": n, "id": t.id, "name": t.name, "lat": t.lat, "lon": t.lon}
               for n, t in enumerate(stops, start=1)],
        path=route["path"],
        distance_m=route["distance_m"],
        duration_s=route["duration_s"],
        steps=steps_from_distance(route["distance_m"]),
        warning=route.get("warning"),
        message=_message(len(stops), len(treasures), label),
    )


def _message(n_stops, n_left, label):
    """What the map says above the stops. If every treasure you can still find is already on the
    loop, the walk is shorter than your goal: say why, so it doesn't look like a mistake."""
    text = f"{n_stops} treasure{'s' if n_stops != 1 else ''} on your {label} loop."
    if n_stops == n_left:
        text += " That's every treasure you haven't found yet, so the loop is shorter than your goal."
    return text

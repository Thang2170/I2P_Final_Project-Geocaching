"""Treasure Trail: POST /api/trail plans a walking loop for a step or time goal (owner: B).

The rules and the algorithm live in trail_planner.py. This file only reads the request,
picks the treasures you can still find, and asks routing.get_route (A's file, unchanged)
for the real walking path of the loop.
"""

from flask import Blueprint, jsonify, request

from auth_api import current_user
from calculator import steps_from_distance
from coin_api import found_treasure_ids
from journey_log import speed_problem
from location import haversine_m
from models import Post, TrailWalk, Treasure, db
from walk_api import _saved_weight, energy_for
from walk_input import DEFAULT_WEIGHT_KG, parse_distance_m, parse_duration_s
from routing import get_route
from location import FOUND_RADIUS_M
from trail_planner import parse_goal, plan_trail, trail_post_text, trail_progress
from weather_api import public_choice, weather_for
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
    weather, choice = weather_for(lat, lon)  # B: shortest in the rain, greener in the heat
    route = get_route([(lat, lon), *[(t.lat, t.lon) for t in stops], (lat, lon)], extra=choice["route_options"])
    return jsonify(
        goal=label,
        stops=[{"order": n, "id": t.id, "name": t.name, "lat": t.lat, "lon": t.lon}
               for n, t in enumerate(stops, start=1)],
        path=route["path"],
        distance_m=route["distance_m"],
        duration_s=route["duration_s"],
        steps=steps_from_distance(route["distance_m"]),
        warning=route.get("warning"),
        weather=public_choice(choice) if weather else None,
        message=_message(len(stops), len(treasures), label),
        start=[lat, lon],  # B: the last checkpoint is back here
    )


@trail_api.route("/api/trail/progress", methods=["POST"])
def progress():
    """B: walking a trail one leg at a time. Python decides when you reached a checkpoint.

    Send JSON: lat, lon (where you are), checkpoints ([[lat, lon], ...] in order, the last one
    back at the start) and index (the checkpoint you were heading to).
    """
    data = request.get_json(silent=True) or {}
    try:
        lat = parse_number(data.get("lat"), "lat", -90, 90)
        lon = parse_number(data.get("lon"), "lon", -180, 180)
        raw = data.get("checkpoints")
        if not isinstance(raw, list) or not 1 <= len(raw) <= 20:
            raise ValueError("checkpoints must be a list of 1 to 20 [lat, lon] points")
        checkpoints = [(parse_number(p[0], "lat", -90, 90), parse_number(p[1], "lon", -180, 180))
                       for p in raw if isinstance(p, (list, tuple)) and len(p) == 2]
        if len(checkpoints) != len(raw):
            raise ValueError("each checkpoint must be [lat, lon]")
        index = data.get("index")
        if not isinstance(index, int) or isinstance(index, bool):
            raise ValueError("index must be a whole number")
        return jsonify(trail_progress((lat, lon), checkpoints, index, FOUND_RADIUS_M))
    except ValueError as err:
        return jsonify(error=str(err)), 400


def _message(n_stops, n_left, label):
    """What the map says above the stops. If every treasure you can still find is already on the
    loop, the walk is shorter than your goal: say why, so it doesn't look like a mistake."""
    text = f"{n_stops} treasure{'s' if n_stops != 1 else ''} on your {label} loop."
    if n_stops == n_left:
        text += " That's every treasure you haven't found yet, so the loop is shorter than your goal."
    return text


MAX_SPLITS = 20


@trail_api.route("/api/trail/walks", methods=["POST"])
def save_trail_walk():
    """B: save a trail walked with the live panel, and post it to the Community.

    Send JSON: distance_m, duration_s, lat, lon (where you finished), start ([lat, lon], where the
    loop began and ends), checkpoints (how many) and splits (seconds at each checkpoint, optional).
    Python checks you are back at the start and that the speed is a walk or a run, and works out
    the steps and calories itself.
    """
    user = current_user()
    if user is None:
        return jsonify(error="Log in first"), 401
    data = request.get_json(silent=True) or {}
    try:
        distance_m = parse_distance_m(data.get("distance_m"))
        duration_s = int(parse_duration_s(data.get("duration_s")))
        lat = parse_number(data.get("lat"), "lat", -90, 90)
        lon = parse_number(data.get("lon"), "lon", -180, 180)
        start = data.get("start")
        if not isinstance(start, list) or len(start) != 2:
            raise ValueError("start must be [lat, lon]")
        start = (parse_number(start[0], "lat", -90, 90), parse_number(start[1], "lon", -180, 180))
        checkpoints = data.get("checkpoints")
        if not isinstance(checkpoints, int) or isinstance(checkpoints, bool) or not 1 <= checkpoints <= 20:
            raise ValueError("checkpoints must be a whole number from 1 to 20")
        splits = data.get("splits") or []
        if not isinstance(splits, list) or len(splits) > MAX_SPLITS:
            raise ValueError(f"splits must be a list of at most {MAX_SPLITS} times")
        splits = [int(parse_number(x, "split", 0, duration_s)) for x in splits]
        if splits != sorted(splits):
            raise ValueError("splits must go up")
    except ValueError as err:
        return jsonify(error=str(err)), 400

    away = haversine_m(lat, lon, start[0], start[1])
    if away > FOUND_RADIUS_M:
        return jsonify(error=f"You are {round(away)} m from the start. A trail ends back where it began."), 400
    problem = speed_problem(distance_m, duration_s)
    if problem:
        return jsonify(error=problem), 400

    weight_kg = _saved_weight(user) or DEFAULT_WEIGHT_KG
    energy = energy_for(user, distance_m, weight_kg, duration_s)
    text = trail_post_text(checkpoints, distance_m, duration_s, energy["steps"], energy["calories"], splits)
    post = Post(user_id=user.id, text=text)
    db.session.add(post)
    db.session.flush()
    walk = TrailWalk(user_id=user.id, checkpoints=checkpoints, distance_m=distance_m, duration_s=duration_s,
                     steps=energy["steps"], calories=energy["calories"], post_id=post.id)
    db.session.add(walk)
    db.session.commit()
    return jsonify(id=walk.id, post_id=post.id, text=text, steps=walk.steps, calories=walk.calories,
                   distance_m=walk.distance_m, duration_s=walk.duration_s), 201

"""Save finished hunts and show the community (Feature 10, owner: B). Rules live in journey_log.py.

Like route_api.py, this lives in its own Blueprint.
The phone only reports what it measured; Python checks it, works out steps and calories,
and decides what is saved.
"""

from flask import Blueprint, jsonify, render_template, request
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from auth_api import current_user
from calculator import calories_from_distance, steps_from_distance
from journey_log import (format_duration, format_pace, parse_journey, rank_players, speed_problem)
from location import FOUND_RADIUS_M, haversine_m
from models import Journey, Treasure, User, db
from walk_api import _saved_weight
from walk_input import DEFAULT_WEIGHT_KG

journey_api = Blueprint("journey_api", __name__)

LEADERBOARD_SIZE = 10
RECENT_SIZE = 20
MINE_SIZE = 50


def _journey_dict(journey, with_player=False):
    data = {
        "id": journey.id,
        "treasure": journey.treasure.name,
        "distance_km": round(journey.distance_m / 1000, 2),
        "time": format_duration(journey.duration_s),
        "pace": format_pace(journey.distance_m, journey.duration_s),
        "steps": journey.steps,
        "calories": journey.calories,
        "when": journey.created_at.isoformat() + "Z",  # stored in UTC; the page shows local time
    }
    if with_player:
        data["username"] = journey.user.username
    return data


def _players():
    """Everyone who finished at least one hunt, ranked. Each row: username, hunts, distance_m, rank."""
    query = (db.select(User.id, User.username, func.count(Journey.id), func.sum(Journey.distance_m))
             .join(Journey, Journey.user_id == User.id).group_by(User.id))
    rows = [{"user_id": uid, "username": name, "hunts": hunts, "distance_m": distance or 0.0}
            for uid, name, hunts, distance in db.session.execute(query)]
    return rank_players(rows)


@journey_api.route("/community")
def community_page():
    return render_template("community.html")


@journey_api.route("/api/journeys", methods=["POST"])
def save_journey():
    """Save a finished hunt. Send JSON: treasure_id, distance_m, duration_s, lat, lon.

    lat and lon are where you stand at the end: you must be within FOUND_RADIUS_M of the treasure.
    """
    user = current_user()
    if user is None:
        return jsonify(error="Log in first"), 401

    try:
        hunt = parse_journey(request.get_json(silent=True))
    except ValueError as err:
        return jsonify(error=str(err)), 400

    treasure = db.session.get(Treasure, hunt["treasure_id"])
    if treasure is None:
        return jsonify(error="No such treasure"), 404
    if treasure.created_by == user.id:
        return jsonify(error="You hid this treasure yourself, so this hunt is not saved."), 403

    away_m = haversine_m(hunt["lat"], hunt["lon"], treasure.lat, treasure.lon)
    if away_m > FOUND_RADIUS_M:
        return jsonify(error=f"You are {round(away_m)} m from the treasure. "
                             f"A hunt is finished within {FOUND_RADIUS_M} m."), 400

    problem = speed_problem(hunt["distance_m"], hunt["duration_s"])
    if problem:
        return jsonify(error=problem), 400

    weight_kg = _saved_weight(user) or DEFAULT_WEIGHT_KG
    journey = Journey(
        user_id=user.id, treasure_id=treasure.id,
        distance_m=hunt["distance_m"], duration_s=hunt["duration_s"],
        steps=steps_from_distance(hunt["distance_m"]),
        calories=round(calories_from_distance(hunt["distance_m"], weight_kg), 1))
    db.session.add(journey)
    try:
        db.session.commit()
    except IntegrityError:  # already saved (or a double tap)
        db.session.rollback()
        return jsonify(error="You already saved this hunt."), 409
    return jsonify(_journey_dict(journey)), 201


@journey_api.route("/api/journeys/mine")
def my_journeys():
    """The logged-in player's saved hunts, newest first, with totals."""
    user = current_user()
    if user is None:
        return jsonify(error="Log in first"), 401
    query = (db.select(Journey).where(Journey.user_id == user.id)
             .order_by(Journey.created_at.desc(), Journey.id.desc()).limit(MINE_SIZE))
    journeys = db.session.execute(query).scalars().all()
    totals = db.session.execute(
        db.select(func.count(Journey.id), func.coalesce(func.sum(Journey.distance_m), 0.0),
                  func.coalesce(func.sum(Journey.steps), 0), func.coalesce(func.sum(Journey.calories), 0.0))
        .where(Journey.user_id == user.id)).one()
    return jsonify(
        journeys=[_journey_dict(j) for j in journeys],
        totals={"hunts": totals[0], "distance_km": round(totals[1] / 1000, 2),
                "steps": totals[2], "calories": round(totals[3], 1)})


@journey_api.route("/api/community")
def community():
    """The leaderboard (most hunts finished) and the latest hunts of everyone."""
    user = current_user()
    if user is None:
        return jsonify(error="Log in first"), 401

    players = _players()
    leaderboard = [{"rank": p["rank"], "username": p["username"], "hunts": p["hunts"],
                    "distance_km": round(p["distance_m"] / 1000, 2), "is_me": p["user_id"] == user.id}
                   for p in players[:LEADERBOARD_SIZE]]
    me = next((p for p in players if p["user_id"] == user.id), None)

    query = (db.select(Journey).order_by(Journey.created_at.desc(), Journey.id.desc()).limit(RECENT_SIZE))
    recent = [_journey_dict(j, with_player=True) for j in db.session.execute(query).scalars().all()]

    return jsonify(
        leaderboard=leaderboard, recent=recent,
        me={"rank": me["rank"], "hunts": me["hunts"], "distance_km": round(me["distance_m"] / 1000, 2)} if me else None,
        players=len(players))

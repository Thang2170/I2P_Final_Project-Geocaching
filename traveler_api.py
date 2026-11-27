"""Traveling treasures (owner: B). Rules: travelers.py.

- GET  /travelers                       the page
- GET  /api/travelers                   every traveler: where it is, its goal, how far it went, its stops
- POST /api/travelers                   {"name", "goal_treasure_id"?, "lat", "lon"}: release one at the treasure you are at
- POST /api/travelers/<id>/pick         {"lat", "lon"}: pick it up (you must be at its treasure)
- POST /api/travelers/<id>/drop         {"lat", "lon"}: drop it at the treasure you are at
"""

from flask import Blueprint, jsonify, redirect, render_template, request

from auth_api import current_user
from models import CoinTransaction, Traveler, TravelerMove, Treasure, User, db
from play_input import parse_position
from travelers import (DROP, GOAL_BONUS, IN_BAG, PICK, RELEASE, distance_text, drop_problem, journey_m,
                       nearest_treasure, parse_traveler, pick_problem, reached_goal, release_problem, stops, where_is)

traveler_api = Blueprint("traveler_api", __name__)

GOAL_REASON = "traveler_goal"
HISTORY_SHOWN = 12


def _moves(traveler_id):
    return db.session.execute(db.select(TravelerMove).filter_by(traveler_id=traveler_id)
                              .order_by(TravelerMove.at, TravelerMove.id)).scalars().all()


def _plain(moves):
    return [(m.action, m.user_id, m.treasure_id) for m in moves]


def _here(lat, lon):
    """The treasure the player is standing at, or None."""
    places = db.session.execute(db.select(Treasure.id, Treasure.lat, Treasure.lon)).all()
    best = nearest_treasure(lat, lon, [tuple(p) for p in places])
    return best[0] if best else None


def _carrying(user_id):
    """How many travelers this player is carrying now."""
    count = 0
    for traveler_id in db.session.execute(db.select(TravelerMove.traveler_id).filter_by(user_id=user_id, action=PICK)
                                          .distinct()).scalars():
        now = where_is(_plain(_moves(traveler_id)))
        count += now["where"] == IN_BAG and now["user_id"] == user_id
    return count


def _traveler_dict(traveler, me, treasures, users):
    moves = _moves(traveler.id)
    if not moves:
        return None  # (only after a demo reset deleted the treasures it visited)
    plain = _plain(moves)
    now = where_is(plain)
    places = [treasures[t] for t in stops(plain)]
    goal_at = reached_goal(plain, traveler.goal_treasure_id)
    goal = treasures.get(traveler.goal_treasure_id)
    if now["where"] == IN_BAG:
        where = "In your bag" if now["user_id"] == me.id else f"In {users[now['user_id']]}'s bag"
    else:
        where = f"At {treasures[now['treasure_id']].name}"
    if goal is None:
        goal_text = "No goal: it just wants to travel."
    elif goal_at is not None:
        goal_text = f"Reached its goal, {goal.name}, thanks to {users[moves[goal_at].user_id]}!"
    else:
        goal_text = f"Wants to reach {goal.name} (+{GOAL_BONUS} coins for whoever drops it there)."
    metres = journey_m([(p.lat, p.lon) for p in places])
    verbs = {RELEASE: "released it at", PICK: "picked it up at", DROP: "dropped it at"}
    history = [{"text": f"{users[m.user_id]} {verbs[m.action]} {treasures[m.treasure_id].name}",
                "at": m.at.isoformat() + "Z"} for m in moves][-HISTORY_SHOWN:]
    return {"id": traveler.id, "name": traveler.name, "creator": users[traveler.created_by],
            "where": where, "in_my_bag": now["where"] == IN_BAG and now["user_id"] == me.id,
            "at_treasure_id": now.get("treasure_id"), "goal": goal_text,
            "goal_reached": goal_at is not None, "travelled": distance_text(metres), "stops": len(places),
            "line": [[p.lat, p.lon] for p in places], "history": list(reversed(history))}


def _lookups():
    treasures = {t.id: t for t in db.session.execute(db.select(Treasure)).scalars()}
    users = dict(db.session.execute(db.select(User.id, User.username)).all())
    return treasures, users


@traveler_api.route("/travelers")
def travelers_page():
    if current_user() is None:
        return redirect("/login?next=/travelers")
    return render_template("travelers.html")


@traveler_api.route("/api/travelers")
def list_travelers():
    me = current_user()
    if me is None:
        return jsonify(error="Log in first"), 401
    treasures, users = _lookups()
    rows = db.session.execute(db.select(Traveler).order_by(Traveler.id)).scalars()
    shown = [_traveler_dict(t, me, treasures, users) for t in rows]
    return jsonify(travelers=[t for t in shown if t is not None],
                   treasures=[{"id": t.id, "name": t.name} for t in sorted(treasures.values(), key=lambda t: t.name)],
                   bonus=GOAL_BONUS)


def _position():
    """(lat, lon, here_treasure_id) or raises ValueError."""
    data = request.get_json(silent=True)
    lat, lon = parse_position(data)
    return data, _here(lat, lon)


@traveler_api.route("/api/travelers", methods=["POST"])
def release():
    me = current_user()
    if me is None:
        return jsonify(error="Log in first"), 401
    try:
        data, here = _position()
        name, goal = parse_traveler(data, set(db.session.execute(db.select(Treasure.id)).scalars()))
    except ValueError as err:
        return jsonify(error=str(err)), 400
    released = db.session.execute(db.select(db.func.count(Traveler.id)).filter_by(created_by=me.id)).scalar_one()
    problem = release_problem(here, released)
    if problem:
        return jsonify(error=problem), 400 if here is None else 409
    if goal == here:
        return jsonify(error="Its goal must be a different treasure from where you release it"), 400
    traveler = Traveler(name=name, goal_treasure_id=goal, created_by=me.id)
    db.session.add(traveler)
    db.session.flush()
    db.session.add(TravelerMove(traveler_id=traveler.id, action=RELEASE, user_id=me.id, treasure_id=here))
    db.session.commit()
    treasures, users = _lookups()
    return jsonify(_traveler_dict(traveler, me, treasures, users)), 201


def _move(traveler_id, action):
    me = current_user()
    if me is None:
        return jsonify(error="Log in first"), 401
    traveler = db.session.get(Traveler, traveler_id)
    if traveler is None:
        return jsonify(error="No such traveler"), 404
    try:
        _, here = _position()
    except ValueError as err:
        return jsonify(error=str(err)), 400
    moves = _plain(_moves(traveler.id))
    if not moves:
        return jsonify(error="No such traveler"), 404
    if action == PICK:
        problem = pick_problem(moves, me.id, here, _carrying(me.id))
    else:
        problem = drop_problem(moves, me.id, here)
    if problem:
        return jsonify(error=problem), 409
    db.session.add(TravelerMove(traveler_id=traveler.id, action=action, user_id=me.id, treasure_id=here))
    db.session.flush()
    bonus = 0
    if action == DROP and reached_goal(moves, traveler.goal_treasure_id) is None \
            and reached_goal(moves + [(DROP, me.id, here)], traveler.goal_treasure_id) is not None:
        bonus = GOAL_BONUS  # the first player to bring it to its goal
        db.session.add(CoinTransaction(user_id=me.id, amount=bonus, reason=GOAL_REASON))
    db.session.commit()
    treasures, users = _lookups()
    data = _traveler_dict(traveler, me, treasures, users)
    place = treasures[here].name
    if action == PICK:
        data["text"] = f"You picked up {traveler.name}. Carry it to another treasure and drop it there."
    elif bonus:
        data["text"] = f"{traveler.name} reached its goal, {place}! +{bonus} coins."
    else:
        data["text"] = f"You left {traveler.name} at {place}. Someone else will carry it on."
    data["coins_earned"] = bonus
    return jsonify(data)


@traveler_api.route("/api/travelers/<int:traveler_id>/pick", methods=["POST"])
def pick(traveler_id):
    return _move(traveler_id, PICK)


@traveler_api.route("/api/travelers/<int:traveler_id>/drop", methods=["POST"])
def drop(traveler_id):
    return _move(traveler_id, DROP)

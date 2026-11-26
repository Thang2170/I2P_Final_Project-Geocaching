"""Hunts players can join, with a waiting line (Feature 8, owner: B).

Rules live in queue_logic.py. Like route_api.py, this lives in its own Blueprint.
"""

from datetime import datetime, timezone

from flask import Blueprint, jsonify, redirect, render_template, request
from sqlalchemy.exc import IntegrityError

from admin_api import online_user_ids  # A: "online now" reuses the live positions of the admin map
from auth_api import current_user
from hunt_chat import can_chat
from hunt_game import join_problem  # A: hunt races (where the hunt goes, Start, winner)
from hunt_game_api import HuntGame, game_dict, game_state_of, parse_treasure_id
from hunt_input import parse_hunt
from models import Hunt, HuntMember, db
from notify_api import notify
from notify_rules import MOVED_UP, moved_up
from queue_logic import count_players, queue_status, status_text

hunt_api = Blueprint("hunt_api", __name__)


def _member_ids(hunt_id):
    """Everyone in the hunt, in the order they joined."""
    query = db.select(HuntMember.user_id).where(HuntMember.hunt_id == hunt_id).order_by(HuntMember.id)
    return db.session.execute(query).scalars().all()


def _hunt_dict(hunt, user):
    member_ids = _member_ids(hunt.id)
    playing, waiting = count_players(len(member_ids), hunt.capacity)
    game = game_dict(hunt, user)
    return {
        "id": hunt.id,
        "name": hunt.name,
        "description": hunt.description,
        "capacity": hunt.capacity,
        "playing": playing,
        "waiting": waiting,
        # A: members who had the map open in the last 2 minutes. Joining is still kept until
        # "Leave" (so nobody loses their place by logging out); this only says who is around now.
        "online": len(online_user_ids(member_ids, datetime.now(timezone.utc))),
        "me": _me(user, member_ids, hunt, game),
        # B: unread group-chat messages, only for players who can open the chat (playing, not in line)
        "unread": _unread(user, hunt, member_ids),
        # A: the race: its treasure, open/started/finished, the winner, and whether you may press Start
        "game": game,
    }


def _me(user, member_ids, hunt, game):
    """B: where you are in this hunt, with the line Python writes for it (queue_logic.status_text)."""
    status = queue_status(user.id, member_ids, hunt.capacity) if user else None
    if status is None:
        return None
    return {**status, "text": status_text(status, finished=bool(game) and game.get("state") == "finished")}


def _unread(user, hunt, member_ids):
    from chat_api import unread_for  # here, not at the top, so the two files don't import each other

    if user is None or not can_chat(user.id, member_ids, hunt.capacity):
        return 0
    return unread_for(user.id, hunt.id)


@hunt_api.route("/hunts")
def hunts_page():
    if current_user() is None:  # B: like every other page: log in first, then come back here
        return redirect("/login?next=/hunts")
    return render_template("hunts.html")


@hunt_api.route("/api/hunts", methods=["GET"])
def list_hunts():
    """Every hunt, newest first. When logged in, each one says where you are in it."""
    user = current_user()
    hunts = db.session.execute(db.select(Hunt).order_by(Hunt.id.desc())).scalars().all()
    result = [_hunt_dict(h, user) for h in hunts]
    db.session.commit()  # A: an old hunt may have just been given its race (hunt_game_api.get_game)
    return jsonify(result)


@hunt_api.route("/api/hunts", methods=["POST"])
def create_hunt():
    """Create a hunt. Send JSON or form fields: name, description, capacity (optional)."""
    user = current_user()
    if user is None:
        return jsonify(error="Log in to create a hunt"), 401

    data = request.get_json(silent=True)
    if data is None:
        data = request.form.to_dict()
    try:
        clean = parse_hunt(data)
        treasure_id = parse_treasure_id(data.get("treasure_id"))  # A: where the hunt goes
    except ValueError as err:
        return jsonify(error=str(err)), 400

    hunt = Hunt(**clean, created_by=user.id)
    db.session.add(hunt)
    db.session.flush()  # gives the hunt its id
    db.session.add(HuntMember(hunt_id=hunt.id, user_id=user.id))  # the creator is the first to join
    if treasure_id is not None:  # A: the race, not started yet (no treasures yet: it gets one later)
        db.session.add(HuntGame(hunt_id=hunt.id, treasure_id=treasure_id))
    db.session.commit()
    return jsonify(_hunt_dict(hunt, user)), 201


@hunt_api.route("/api/hunts/<int:hunt_id>/join", methods=["POST"])
def join_hunt(hunt_id):
    user = current_user()
    if user is None:
        return jsonify(error="Log in to join a hunt"), 401
    hunt = db.session.get(Hunt, hunt_id)
    if hunt is None:
        return jsonify(error="No such hunt"), 404
    if user.id in _member_ids(hunt_id):
        return jsonify(error="You already joined this hunt."), 409
    problem = join_problem(game_state_of(hunt_id))  # A: no joining a race that already started
    if problem:
        return jsonify(error=problem), 409

    db.session.add(HuntMember(hunt_id=hunt_id, user_id=user.id))
    try:
        db.session.commit()
    except IntegrityError:  # a double tap: the other request joined you a moment ago
        db.session.rollback()
        return jsonify(error="You already joined this hunt."), 409
    return jsonify(_hunt_dict(hunt, user))


@hunt_api.route("/api/hunts/<int:hunt_id>/leave", methods=["POST"])
def leave_hunt(hunt_id):
    """Leave a hunt. Whoever is next in line moves up by itself."""
    user = current_user()
    if user is None:
        return jsonify(error="Log in first"), 401
    hunt = db.session.get(Hunt, hunt_id)
    if hunt is None:
        return jsonify(error="No such hunt"), 404

    membership = db.session.execute(
        db.select(HuntMember).where(HuntMember.hunt_id == hunt_id, HuntMember.user_id == user.id)
    ).scalar_one_or_none()
    if membership is None:
        return jsonify(error="You are not in this hunt."), 409

    before = _member_ids(hunt_id)
    db.session.delete(membership)
    db.session.flush()
    # B: whoever moves up from the waiting line gets a notification (the bell in the top bar)
    for risen in moved_up(before, _member_ids(hunt_id), hunt.capacity):
        notify(risen, MOVED_UP, hunt_id=hunt.id)
    db.session.commit()
    return jsonify(_hunt_dict(hunt, user))

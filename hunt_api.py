"""Hunts players can join, with a waiting line (Feature 8, owner: B).

Rules live in queue_logic.py. Like route_api.py, this lives in its own Blueprint.
"""

from flask import Blueprint, jsonify, render_template, request
from sqlalchemy.exc import IntegrityError

from auth_api import current_user
from hunt_input import parse_hunt
from models import Hunt, HuntMember, db
from queue_logic import count_players, queue_status

hunt_api = Blueprint("hunt_api", __name__)


def _member_ids(hunt_id):
    """Everyone in the hunt, in the order they joined."""
    query = db.select(HuntMember.user_id).where(HuntMember.hunt_id == hunt_id).order_by(HuntMember.id)
    return db.session.execute(query).scalars().all()


def _hunt_dict(hunt, user):
    member_ids = _member_ids(hunt.id)
    playing, waiting = count_players(len(member_ids), hunt.capacity)
    return {
        "id": hunt.id,
        "name": hunt.name,
        "description": hunt.description,
        "capacity": hunt.capacity,
        "playing": playing,
        "waiting": waiting,
        "me": queue_status(user.id, member_ids, hunt.capacity) if user else None,
    }


@hunt_api.route("/hunts")
def hunts_page():
    return render_template("hunts.html")


@hunt_api.route("/api/hunts", methods=["GET"])
def list_hunts():
    """Every hunt, newest first. When logged in, each one says where you are in it."""
    user = current_user()
    hunts = db.session.execute(db.select(Hunt).order_by(Hunt.id.desc())).scalars().all()
    return jsonify([_hunt_dict(h, user) for h in hunts])


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
    except ValueError as err:
        return jsonify(error=str(err)), 400

    hunt = Hunt(**clean, created_by=user.id)
    db.session.add(hunt)
    db.session.flush()  # gives the hunt its id
    db.session.add(HuntMember(hunt_id=hunt.id, user_id=user.id))  # the creator is the first to join
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

    db.session.delete(membership)
    db.session.commit()
    return jsonify(_hunt_dict(hunt, user))

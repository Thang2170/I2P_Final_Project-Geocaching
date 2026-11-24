"""The active journey, kept on the server so it survives a lost connection (owner: A).

Rules live in journey_resume.py. Endpoints:

    POST   /api/journeys/active           {"treasure_id", "lat", "lon"}  start (or restart) it
    POST   /api/journeys/active/progress  {"meters", "elapsed_s"}        save how far you got
    GET    /api/journeys/active                                          carry on after a reload
    DELETE /api/journeys/active                                          finished or cancelled

Its own table (active_journeys), so an existing geohunt.db gets it without being deleted.
"""

from datetime import datetime, timezone

from flask import Blueprint, jsonify, request

from auth_api import current_user
from journey_resume import (as_utc, can_resume, deadline_for, parse_progress, resume_window_s,
                            seconds_left)
from live_positions import parse_position
from location import haversine_m
from models import Treasure, db

journey_resume_api = Blueprint("journey_resume_api", __name__)


class ActiveJourney(db.Model):
    """The journey a player is on now. One row per player at most."""

    __tablename__ = "active_journeys"
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), primary_key=True)
    treasure_id = db.Column(db.Integer, db.ForeignKey("treasures.id"), nullable=False)
    started_at = db.Column(db.DateTime, nullable=False)
    deadline = db.Column(db.DateTime, nullable=False)
    meters = db.Column(db.Float, nullable=False, default=0.0)      # walked so far (last report)
    elapsed_s = db.Column(db.Integer, nullable=False, default=0)   # clock time so far (last report)
    updated_at = db.Column(db.DateTime, nullable=False)


def _now():
    return datetime.now(timezone.utc)


def _journey_dict(active, now):
    treasure = db.session.get(Treasure, active.treasure_id)
    return {
        "treasure": treasure.to_dict() if treasure else None,
        "started_at": as_utc(active.started_at).isoformat(),
        "deadline": as_utc(active.deadline).isoformat(),
        "seconds_left": seconds_left(active.deadline, now),
        "meters": active.meters,
        "elapsed_s": active.elapsed_s,
        # how long ago the phone last reported, so the clock can catch up after a reload
        "since_update_s": max(0, int((as_utc(now) - as_utc(active.updated_at)).total_seconds())),
    }


@journey_resume_api.route("/api/journeys/active", methods=["POST"])
def start_active():
    user = current_user()
    if user is None:
        return jsonify(error="Log in first"), 401
    data = request.get_json(silent=True)
    try:
        lat, lon = parse_position(data)
        treasure_id = int(data.get("treasure_id"))
    except (ValueError, TypeError):
        return jsonify(error="Send treasure_id, lat and lon"), 400
    treasure = db.session.get(Treasure, treasure_id)
    if treasure is None:
        return jsonify(error="No such treasure"), 404

    now = _now()
    straight_m = haversine_m(lat, lon, treasure.lat, treasure.lon)
    active = db.session.get(ActiveJourney, user.id) or ActiveJourney(user_id=user.id)
    active.treasure_id = treasure.id
    active.started_at = now
    active.deadline = deadline_for(now, straight_m)
    active.meters, active.elapsed_s, active.updated_at = 0.0, 0, now
    db.session.add(active)
    db.session.commit()
    return jsonify(window_s=resume_window_s(straight_m), **_journey_dict(active, now)), 201


@journey_resume_api.route("/api/journeys/active/progress", methods=["POST"])
def save_progress():
    user = current_user()
    if user is None:
        return jsonify(error="Log in first"), 401
    try:
        meters, elapsed = parse_progress(request.get_json(silent=True))
    except ValueError as err:
        return jsonify(error=str(err)), 400
    active = db.session.get(ActiveJourney, user.id)
    now = _now()
    if active is None or not can_resume(active.deadline, now):
        return jsonify(error="No journey to carry on (it finished or ran out of time)."), 404
    # Never go backwards: a late, old report must not undo a newer one
    active.meters = max(active.meters, meters)
    active.elapsed_s = max(active.elapsed_s, elapsed)
    active.updated_at = now
    db.session.commit()
    return jsonify(_journey_dict(active, now))


@journey_resume_api.route("/api/journeys/active", methods=["GET"])
def get_active():
    """The journey to carry on, or {"active": null}. An expired one is reported once, then forgotten."""
    user = current_user()
    if user is None:
        return jsonify(error="Log in first"), 401
    active = db.session.get(ActiveJourney, user.id)
    if active is None:
        return jsonify(active=None)
    now = _now()
    if not can_resume(active.deadline, now):
        treasure = db.session.get(Treasure, active.treasure_id)
        db.session.delete(active)
        db.session.commit()
        return jsonify(active=None, expired={"treasure": treasure.name if treasure else None})
    return jsonify(active=_journey_dict(active, now))


@journey_resume_api.route("/api/journeys/active", methods=["DELETE"])
def end_active():
    user = current_user()
    if user is None:
        return jsonify(error="Log in first"), 401
    active = db.session.get(ActiveJourney, user.id)
    if active is not None:
        db.session.delete(active)
        db.session.commit()
    return jsonify(ok=True)

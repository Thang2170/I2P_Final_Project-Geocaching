"""Walking modes: try-hard and calm walks (owner: B). Rules live in modes.py.

- GET  /api/mode                                 your mode (normal if you never picked one)
- POST /api/mode            {mode}               pick normal, tryhard or calm
- GET  /api/mode/pace?distance_m=..&duration_s=..  try-hard: are you on pace? (Python decides)
- GET  /api/calm-spots                           the calm treasures with today's mindful prompt
A saved hunt calls pay_mode_bonus() (journey_api.py).
"""

from datetime import datetime, timezone

from flask import Blueprint, jsonify, request
from sqlalchemy.exc import IntegrityError

from auth_api import current_user
from models import CoinTransaction, ModeBonus, Treasure, WalkMode, db
from modes import (MODE_TEXT, MODES, calm_bonus, calm_spot, pace_status, parse_mode, tryhard_bonus)
from streaks import local_day
from walk_input import parse_distance_m, parse_duration_s

mode_api = Blueprint("mode_api", __name__)

TRYHARD_REASON = "tryhard_bonus"
CALM_REASON = "calm_bonus"


def mode_of(user):
    row = db.session.get(WalkMode, user.id) if user else None
    return row.mode if row else "normal"


def _today():
    return local_day(datetime.now(timezone.utc))


def _mode_dict(mode):
    return {"mode": mode, "title": MODES[mode], "text": MODE_TEXT[mode],
            "choices": [{"id": k, "title": v, "text": MODE_TEXT[k]} for k, v in MODES.items()]}


@mode_api.route("/api/mode")
def get_mode():
    user = current_user()
    if user is None:
        return jsonify(error="Log in first"), 401
    return jsonify(_mode_dict(mode_of(user)))


@mode_api.route("/api/mode", methods=["POST"])
def set_mode():
    user = current_user()
    if user is None:
        return jsonify(error="Log in first"), 401
    data = request.get_json(silent=True) or {}
    try:
        mode = parse_mode(data.get("mode") if isinstance(data, dict) else None)
    except ValueError as err:
        return jsonify(error=str(err)), 400
    row = db.session.get(WalkMode, user.id) or WalkMode(user_id=user.id, mode=mode)
    row.mode = mode
    db.session.add(row)
    db.session.commit()
    return jsonify(_mode_dict(mode))


@mode_api.route("/api/mode/pace")
def pace():
    try:
        distance_m = parse_distance_m(request.args.get("distance_m"))
        duration_s = parse_duration_s(request.args.get("duration_s"))
    except ValueError as err:
        return jsonify(error=str(err)), 400
    return jsonify(pace_status(distance_m, duration_s))


@mode_api.route("/api/calm-spots")
def calm_spots():
    today = _today()
    spots = []
    for t in db.session.execute(db.select(Treasure).order_by(Treasure.id)).scalars():
        spot = calm_spot(t.id, t.name, t.description, today)
        if spot:
            spots.append({"id": t.id, "name": t.name} | spot)
    return jsonify(spots=spots)


def pay_mode_bonus(user, journey, treasure):
    """Called once a hunt is saved. Returns {"mode", "coins", "text"} or None in normal mode."""
    mode = mode_of(user)
    if mode == "tryhard":
        coins, text = tryhard_bonus(journey.distance_m, journey.duration_s)
        reason = TRYHARD_REASON
    elif mode == "calm":
        coins, text = calm_bonus(calm_spot(treasure.id, treasure.name, treasure.description) is not None,
                                 journey.duration_s)
        reason = CALM_REASON
    else:
        return None
    db.session.add(ModeBonus(journey_id=journey.id, user_id=user.id, mode=mode, coins=coins))
    if coins:
        db.session.add(CoinTransaction(user_id=user.id, amount=coins, reason=reason))
    try:
        db.session.commit()
    except IntegrityError:  # already paid for this hunt
        db.session.rollback()
        return None
    return {"mode": mode, "coins": coins, "text": text}

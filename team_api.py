"""Team treasures (owner: B). Rules: team_lock.py.

- GET    /team                                  the page
- GET    /api/team-locks                        every team treasure: who is there now, did it open for you
- POST   /api/treasures/<id>/team-lock          {"need": 2 or 3} (who hid it, or an admin)
- DELETE /api/treasures/<id>/team-lock
- POST   /api/team-locks/<lock_id>/here         {"lat", "lon"}: "I'm here". Opens it when enough are here.

While a treasure has a team lock, coin_api.py refuses to pay for it until it opened for you.
"""

from datetime import datetime, timedelta, timezone

from flask import Blueprint, jsonify, redirect, render_template, request
from sqlalchemy.exc import IntegrityError

from admin_api import is_admin
from auth_api import current_user
from location import FOUND_RADIUS_M, haversine_m
from models import CoinTransaction, TeamCheckin, TeamLock, TeamOpen, Treasure, User, db
from play_input import may_manage, parse_position
from team_lock import TEAM_BONUS, WINDOW_S, claim_refusal_text, here_now, parse_need, status_text, who_opens

team_api = Blueprint("team_api", __name__)

BONUS_REASON = "team_treasure"


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)  # naive UTC, like the database (tests patch this)


def _lock(treasure_id):
    return db.session.execute(db.select(TeamLock).filter_by(treasure_id=treasure_id)).scalar_one_or_none()


def _opened_ids(lock_id):
    return set(db.session.execute(db.select(TeamOpen.user_id).filter_by(lock_id=lock_id)).scalars())


def claim_refusal(treasure, user_id):
    """For coin_api.py: a message if this is a team treasure that has not opened for the player."""
    lock = _lock(treasure.id)
    if lock is None or user_id in _opened_ids(lock.id):
        return None
    return claim_refusal_text(lock.need)


def _names(ids):
    if not ids:
        return []
    return sorted(db.session.execute(db.select(User.username).where(User.id.in_(ids))).scalars())


def _lock_dict(lock, treasure, me, now):
    checkins = db.session.execute(db.select(TeamCheckin.user_id, TeamCheckin.at).filter_by(lock_id=lock.id)).all()
    here = here_now(checkins, now)
    opened = _opened_ids(lock.id)
    return {"id": lock.id, "treasure_id": treasure.id, "treasure": treasure.name,
            "lat": treasure.lat, "lon": treasure.lon, "need": lock.need,
            "here": _names(here), "me_here": me.id in here, "opened": me.id in opened,
            "opened_by": len(opened), "bonus": TEAM_BONUS,
            "text": status_text(lock.need, len(here), me.id in opened),
            "mine": may_manage(me.id, treasure.created_by, is_admin(me))}


@team_api.route("/team")
def team_page():
    if current_user() is None:
        return redirect("/login?next=/team")
    return render_template("team.html")


@team_api.route("/api/team-locks")
def list_locks():
    me = current_user()
    if me is None:
        return jsonify(error="Log in first"), 401
    now = _now()
    rows = db.session.execute(db.select(TeamLock, Treasure).join(Treasure, Treasure.id == TeamLock.treasure_id)
                              .order_by(Treasure.name)).all()
    locks = [_lock_dict(lock, treasure, me, now) for lock, treasure in rows]
    locked = {lock["treasure_id"] for lock in locks}
    admin = is_admin(me)
    can_add = [{"id": t.id, "name": t.name} for t in db.session.execute(db.select(Treasure).order_by(Treasure.name)).scalars()
               if t.id not in locked and may_manage(me.id, t.created_by, admin)]
    return jsonify(locks=locks, can_add=can_add, window_s=WINDOW_S)


def _managed_treasure(treasure_id):
    me = current_user()
    if me is None:
        return None, (jsonify(error="Log in first"), 401)
    treasure = db.session.get(Treasure, treasure_id)
    if treasure is None:
        return None, (jsonify(error="No such treasure"), 404)
    if not may_manage(me.id, treasure.created_by, is_admin(me)):
        return None, (jsonify(error="Only the player who hid this treasure can make it a team treasure"), 403)
    return treasure, None


@team_api.route("/api/treasures/<int:treasure_id>/team-lock", methods=["POST"])
def add_lock(treasure_id):
    treasure, error = _managed_treasure(treasure_id)
    if error:
        return error
    data = request.get_json(silent=True) or {}
    try:
        need = parse_need(data.get("need") if isinstance(data, dict) else None)
    except ValueError as err:
        return jsonify(error=str(err)), 400
    if _lock(treasure.id) is not None:
        return jsonify(error="This is already a team treasure"), 409
    db.session.add(TeamLock(treasure_id=treasure.id, need=need, created_by=current_user().id))
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify(error="This is already a team treasure"), 409
    return jsonify(treasure=treasure.name, need=need), 201


@team_api.route("/api/treasures/<int:treasure_id>/team-lock", methods=["DELETE"])
def remove_lock(treasure_id):
    treasure, error = _managed_treasure(treasure_id)
    if error:
        return error
    lock = _lock(treasure.id)
    if lock is None:
        return jsonify(error="This is not a team treasure"), 404
    db.session.execute(db.delete(TeamCheckin).where(TeamCheckin.lock_id == lock.id))
    db.session.execute(db.delete(TeamOpen).where(TeamOpen.lock_id == lock.id))
    db.session.delete(lock)
    db.session.commit()
    return jsonify(ok=True)


@team_api.route("/api/team-locks/<int:lock_id>/here", methods=["POST"])
def im_here(lock_id):
    me = current_user()
    if me is None:
        return jsonify(error="Log in first"), 401
    lock = db.session.get(TeamLock, lock_id)
    if lock is None:
        return jsonify(error="No such team treasure"), 404
    treasure = db.session.get(Treasure, lock.treasure_id)
    try:
        lat, lon = parse_position(request.get_json(silent=True))
    except ValueError as err:
        return jsonify(error=str(err)), 400
    distance = haversine_m(lat, lon, treasure.lat, treasure.lon)
    if distance > FOUND_RADIUS_M:
        return jsonify(error=f"You are {round(distance)} m away. Stand within {FOUND_RADIUS_M} m of "
                             f"{treasure.name} first."), 400

    now = _now()
    db.session.execute(db.delete(TeamCheckin).where(TeamCheckin.lock_id == lock.id,
                                                    TeamCheckin.at < now - timedelta(seconds=WINDOW_S)))
    db.session.add(TeamCheckin(lock_id=lock.id, user_id=me.id, at=now))
    db.session.flush()
    checkins = db.session.execute(db.select(TeamCheckin.user_id, TeamCheckin.at).filter_by(lock_id=lock.id)).all()
    newly = who_opens(lock.need, here_now(checkins, now), _opened_ids(lock.id))
    for user_id in newly:
        db.session.add(TeamOpen(lock_id=lock.id, user_id=user_id, at=now))
        db.session.add(CoinTransaction(user_id=user_id, amount=TEAM_BONUS, reason=BONUS_REASON))
    try:
        db.session.commit()
    except IntegrityError:  # two taps opened it at the same moment: the other one paid
        db.session.rollback()
    data = _lock_dict(lock, treasure, me, now)
    data["just_opened"] = me.id in newly
    if data["just_opened"]:
        data["text"] = f"Open! {', '.join(data['here'])} opened it together: +{TEAM_BONUS} coins each. Now find it on the map."
    return jsonify(data)

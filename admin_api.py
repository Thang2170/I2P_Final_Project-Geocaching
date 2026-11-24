"""Admin page for the live demo (owner: A).

While a teammate plays on a phone, the audience watches this page: the totals
and the latest actions refresh every few seconds, and every treasure is on a map.

Who may open it: logged-in players whose username is in the ADMIN_USERS
environment variable (comma-separated). Without the variable, only "admin".

Like route_api.py, this lives in its own Blueprint. app.py only needs:

    from admin_api import admin_api
    app.register_blueprint(admin_api)
"""

import os
from datetime import datetime, timezone

from flask import Blueprint, jsonify, redirect, render_template, request, url_for
from sqlalchemy import func

from auth_api import current_user
from coin_api import FOUND_REASON
from live_positions import is_live, parse_position, seconds_ago
from models import CoinTransaction, Hunt, HuntMember, Purchase, Treasure, User, db
from photo_api import photo_url
from treasure_checks import set_verified, verified_ids
from crossing_marks import ManualCrossing, all_manual, parse_kind

admin_api = Blueprint("admin_api", __name__)


class PlayerPosition(db.Model):
    """Where each player was last seen, for the admin's live map.

    One row per player (user_id is the key): each update REPLACES the old position,
    so we never keep a history of where someone walked. It lives here and not in
    models.py so A doesn't change B's file. app.py imports this file before
    db.create_all(), so the table is made in an existing database too.
    """

    __tablename__ = "player_positions"
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), primary_key=True)
    lat = db.Column(db.Float, nullable=False)
    lon = db.Column(db.Float, nullable=False)
    updated_at = db.Column(db.DateTime, nullable=False)

DEFAULT_ADMINS = "admin"
EVENTS_SHOWN = 15


def admin_names():
    """The usernames allowed on the admin page, read from ADMIN_USERS."""
    raw = os.environ.get("ADMIN_USERS", DEFAULT_ADMINS)
    return {name.strip() for name in raw.split(",") if name.strip()}


def is_admin(user):
    return user is not None and user.username in admin_names()


def _event(when, who, what):
    """One line of the activity feed. `when` is a datetime; the browser only shows the time."""
    # SQLite gives the time back without a zone. It was saved as UTC, so say so,
    # or the browser would read it as local time and be hours off.
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return {"when": when.isoformat(), "who": who, "what": what}


def recent_events():
    """The latest things that happened, newest first, as plain dicts."""
    events = []
    rows = db.session.execute(
        db.select(User.created_at, User.username).order_by(User.id.desc()).limit(EVENTS_SHOWN)).all()
    events += [_event(when, who, "joined StepQuest") for when, who in rows]

    rows = db.session.execute(
        db.select(Treasure.created_at, User.username, Treasure.name)
        .join(User, User.id == Treasure.created_by)
        .order_by(Treasure.id.desc()).limit(EVENTS_SHOWN)).all()
    events += [_event(when, who, f'hid "{name}"') for when, who, name in rows]

    rows = db.session.execute(
        db.select(CoinTransaction.created_at, User.username, CoinTransaction.amount, Treasure.name)
        .join(User, User.id == CoinTransaction.user_id)
        .join(Treasure, Treasure.id == CoinTransaction.treasure_id)
        .where(CoinTransaction.reason == FOUND_REASON)
        .order_by(CoinTransaction.id.desc()).limit(EVENTS_SHOWN)).all()
    events += [_event(when, who, f'found "{name}" (+{amount} coins)') for when, who, amount, name in rows]

    rows = db.session.execute(
        db.select(Purchase.created_at, User.username, Purchase.item_id, Purchase.price)
        .join(User, User.id == Purchase.user_id)
        .order_by(Purchase.id.desc()).limit(EVENTS_SHOWN)).all()
    events += [_event(when, who, f"bought {item} for {price} coins") for when, who, item, price in rows]

    rows = db.session.execute(
        db.select(HuntMember.joined_at, User.username, Hunt.name)
        .join(User, User.id == HuntMember.user_id)
        .join(Hunt, Hunt.id == HuntMember.hunt_id)
        .order_by(HuntMember.id.desc()).limit(EVENTS_SHOWN)).all()
    events += [_event(when, who, f'joined the hunt "{name}"') for when, who, name in rows]

    events.sort(key=lambda e: e["when"], reverse=True)
    return events[:EVENTS_SHOWN]


def online_user_ids(user_ids, now):
    """Which of these players sent a position in the last LIVE_WINDOW_S seconds.

    Used by the Hunts page to say how many members are online now. Only a count
    leaves this file there, never a position.
    """
    if not user_ids:
        return set()
    rows = db.session.execute(
        db.select(PlayerPosition).where(PlayerPosition.user_id.in_(user_ids))).scalars().all()
    return {pos.user_id for pos in rows if is_live(pos.updated_at, now)}


def live_players(now, user_ids=None):
    """Players seen in the last LIVE_WINDOW_S seconds, as plain dicts sorted by name.

    user_ids: only these players (the hunt map shows just its own members). None = everyone.
    """
    query = (db.select(User.username, PlayerPosition)
             .join(PlayerPosition, PlayerPosition.user_id == User.id)
             .order_by(User.username))
    if user_ids is not None:
        query = query.where(User.id.in_(user_ids))
    rows = db.session.execute(query).all()
    return [{"name": name, "lat": pos.lat, "lon": pos.lon,
             "seconds_ago": seconds_ago(pos.updated_at, now)}
            for name, pos in rows if is_live(pos.updated_at, now)]


def _count(query):
    return db.session.execute(query).scalar_one()


def summary():
    """Everything the admin page shows, as one dict."""
    treasures = db.session.execute(db.select(Treasure).order_by(Treasure.id)).scalars().all()
    creators = {u.id: u.username for u in db.session.execute(db.select(User)).scalars().all()}
    verified = verified_ids()
    return {
        "players": _count(db.select(func.count(User.id))),
        "treasures": len(treasures),
        "finds": _count(db.select(func.count(CoinTransaction.id))
                        .where(CoinTransaction.reason == FOUND_REASON)),
        "coins_paid": _count(db.select(func.coalesce(func.sum(CoinTransaction.amount), 0))
                             .where(CoinTransaction.reason == FOUND_REASON)),
        "hunts": _count(db.select(func.count(Hunt.id))),
        "treasure_list": [{**t.to_dict(), "creator": creators.get(t.created_by, "demo"),
                           "photo_url": photo_url(t.id), "verified": t.id in verified} for t in treasures],
        "unverified": sum(1 for t in treasures if t.id not in verified),
        "events": recent_events(),
        "live_players": live_players(datetime.now(timezone.utc)),
        "crossings": all_manual(),  # A: street crossings added by hand (Feature 7)
    }


@admin_api.route("/admin")
def admin_page():
    user = current_user()
    if user is None:
        return redirect(url_for("auth_api.login_page", next=request.path))
    if not is_admin(user):
        return render_template("admin.html", allowed=False, username=user.username), 403
    return render_template("admin.html", allowed=True, username=user.username)


@admin_api.route("/api/admin/summary")
def admin_summary():
    """The live numbers, the treasure list and the latest actions. Admins only."""
    user = current_user()
    if user is None:
        return jsonify(error="Log in first"), 401
    if not is_admin(user):
        return jsonify(error="This page is for admins"), 403
    return jsonify(summary())


@admin_api.route("/api/me/position", methods=["POST"])
def save_position():
    """The map page sends {"lat": .., "lon": ..} every few seconds while you play.

    Saved so the admin's live map can show you. Only your last position is kept.
    """
    user = current_user()
    if user is None:
        return jsonify(error="Log in first"), 401
    try:
        lat, lon = parse_position(request.get_json(silent=True))
    except ValueError as err:
        return jsonify(error=str(err)), 400

    position = db.session.get(PlayerPosition, user.id)
    if position is None:  # first time: make this player's one row
        position = PlayerPosition(user_id=user.id)
        db.session.add(position)
    position.lat, position.lon = lat, lon
    position.updated_at = datetime.now(timezone.utc)
    db.session.commit()
    return jsonify(ok=True)


@admin_api.route("/api/admin/treasures/<int:treasure_id>/verify", methods=["POST"])
def verify_treasure(treasure_id):
    """Admins only. Send JSON {"verified": true} to check a treasure, false to take it back."""
    user = current_user()
    if user is None:
        return jsonify(error="Log in first"), 401
    if not is_admin(user):
        return jsonify(error="This page is for admins"), 403
    data = request.get_json(silent=True)
    wanted = data.get("verified", True) if isinstance(data, dict) else True
    if not isinstance(wanted, bool):
        return jsonify(error="verified must be true or false"), 400
    if not set_verified(treasure_id, user.id, wanted):
        return jsonify(error="No such treasure"), 404
    db.session.commit()
    return jsonify(treasure_id=treasure_id, verified=treasure_id in verified_ids())


def _admin_or_error():
    """(user, None) for an admin, else (None, error response)."""
    user = current_user()
    if user is None:
        return None, (jsonify(error="Log in first"), 401)
    if not is_admin(user):
        return None, (jsonify(error="This page is for admins"), 403)
    return user, None


@admin_api.route("/api/admin/crossings", methods=["POST"])
def add_crossing():
    """Admins only. {"lat", "lon", "kind" (optional)}: a street crossing OpenStreetMap doesn't know."""
    user, error = _admin_or_error()
    if error:
        return error
    data = request.get_json(silent=True)
    try:
        lat, lon = parse_position(data)
        kind = parse_kind(data.get("kind"))
    except ValueError as err:
        return jsonify(error=str(err)), 400
    crossing = ManualCrossing(lat=lat, lon=lon, kind=kind, added_by=user.id)
    db.session.add(crossing)
    db.session.commit()
    return jsonify(crossing.to_dict()), 201


@admin_api.route("/api/admin/crossings/<int(signed=True):crossing_id>", methods=["DELETE"])
def remove_crossing(crossing_id):
    """Admins only. The id is the map id (negative), as sent by the summary."""
    user, error = _admin_or_error()
    if error:
        return error
    crossing = db.session.get(ManualCrossing, abs(crossing_id))
    if crossing is None:
        return jsonify(error="No such crossing"), 404
    db.session.delete(crossing)
    db.session.commit()
    return jsonify(ok=True)

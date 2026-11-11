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
from datetime import timezone

from flask import Blueprint, jsonify, redirect, render_template, request, url_for
from sqlalchemy import func

from auth_api import current_user
from coin_api import FOUND_REASON
from models import CoinTransaction, Hunt, HuntMember, Purchase, Treasure, User, db
from photo_api import photo_url

admin_api = Blueprint("admin_api", __name__)

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


def _count(query):
    return db.session.execute(query).scalar_one()


def summary():
    """Everything the admin page shows, as one dict."""
    treasures = db.session.execute(db.select(Treasure).order_by(Treasure.id)).scalars().all()
    creators = {u.id: u.username for u in db.session.execute(db.select(User)).scalars().all()}
    return {
        "players": _count(db.select(func.count(User.id))),
        "treasures": len(treasures),
        "finds": _count(db.select(func.count(CoinTransaction.id))
                        .where(CoinTransaction.reason == FOUND_REASON)),
        "coins_paid": _count(db.select(func.coalesce(func.sum(CoinTransaction.amount), 0))
                             .where(CoinTransaction.reason == FOUND_REASON)),
        "hunts": _count(db.select(func.count(Hunt.id))),
        "treasure_list": [{**t.to_dict(), "creator": creators.get(t.created_by, "demo"),
                           "photo_url": photo_url(t.id)} for t in treasures],
        "events": recent_events(),
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

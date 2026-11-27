"""The wandering treasure (owner: B). Rules: wanderer.py.

- GET  /wanderer                 the page
- GET  /api/wanderer             its footprints (never where it is), and whether you caught it today
- POST /api/wanderer/catch       {"lat", "lon"}: is it here? Pays wanderer.CATCH_COINS once a day

Its walk comes from a seed made from the app's SECRET_KEY, so the code on GitHub does not
give away where it is. Admins can add ?reveal=1 to see it (for a presentation).
"""

import hashlib
import hmac
import time
from datetime import datetime, timezone

from flask import Blueprint, current_app, jsonify, redirect, render_template, request
from sqlalchemy.exc import IntegrityError

from admin_api import is_admin
from auth_api import current_user
from models import CoinTransaction, WandererCatch, db
from play_input import parse_position
from streaks import local_day
from wanderer import (CATCH_COINS, CATCH_RADIUS_M, CAUGHT, FOOTPRINT_STEP_S, HOME, RADIUS_M, footprints,
                      metres_per_day, position_at, try_catch)

wanderer_api = Blueprint("wanderer_api", __name__)

CATCH_REASON = "wanderer_catch"


def _now():
    return time.time()  # (tests patch this)


def seed_for(app):
    """The walk's seed: secret, but the same for every player and every restart."""
    key = str(app.config["SECRET_KEY"]).encode()
    return int.from_bytes(hmac.new(key, b"wandering treasure", hashlib.sha256).digest()[:8], "big")


def _today(now):
    return local_day(datetime.fromtimestamp(now, timezone.utc))


def _caught_today(user_id, now):
    return db.session.execute(db.select(WandererCatch.id).filter_by(user_id=user_id, day=_today(now))).first() is not None


@wanderer_api.route("/wanderer")
def wanderer_page():
    if current_user() is None:
        return redirect("/login?next=/wanderer")
    return render_template("wanderer.html")


@wanderer_api.route("/api/wanderer")
def footprints_api():
    me = current_user()
    if me is None:
        return jsonify(error="Log in first"), 401
    now, seed = _now(), seed_for(current_app)
    data = {"footprints": footprints(now, seed), "home": {"lat": HOME[0], "lon": HOME[1]}, "radius_m": RADIUS_M,
            "catch_radius_m": CATCH_RADIUS_M, "coins": CATCH_COINS, "walked_today_m": metres_per_day(now, seed),
            "caught_today": _caught_today(me.id, now), "refresh_s": FOOTPRINT_STEP_S}
    if request.args.get("reveal") == "1" and is_admin(me):
        lat, lon = position_at(now, seed)
        data["now"] = {"lat": round(lat, 6), "lon": round(lon, 6)}
    return jsonify(data)


@wanderer_api.route("/api/wanderer/catch", methods=["POST"])
def catch():
    me = current_user()
    if me is None:
        return jsonify(error="Log in first"), 401
    try:
        lat, lon = parse_position(request.get_json(silent=True))
    except ValueError as err:
        return jsonify(error=str(err)), 400
    now = _now()
    result, hint = try_catch(lat, lon, now, seed_for(current_app))
    if result != CAUGHT:
        return jsonify(result=result, text=hint, coins_earned=0)
    if _caught_today(me.id, now):
        return jsonify(result=result, text="You caught it again! One reward a day: come back tomorrow.", coins_earned=0)
    db.session.add(WandererCatch(user_id=me.id, day=_today(now)))
    db.session.add(CoinTransaction(user_id=me.id, amount=CATCH_COINS, reason=CATCH_REASON))
    try:
        db.session.commit()
    except IntegrityError:  # a double tap
        db.session.rollback()
        return jsonify(result=result, text="You caught it again! One reward a day: come back tomorrow.", coins_earned=0)
    return jsonify(result=result, text=f"{hint} +{CATCH_COINS} coins.", coins_earned=CATCH_COINS)

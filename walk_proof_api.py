"""Prove you walked: keep a short GPS trail, check finds, and let admins review (owner: B).

The rules live in walk_proof.py. This file:
- record_point(): called by /api/me/position (admin_api.py) every time the map sends a position;
- check_find(): called by the treasure claim (coin_api.py) before paying;
- flag_find(): saves a suspicious find for the admin page;
- GET  /api/admin/suspicious-finds              the finds waiting for an admin
- POST /api/admin/suspicious-finds/<id>          {"action": "keep"} or {"action": "reverse"}
"""

from datetime import datetime, timedelta, timezone

from flask import Blueprint, current_app, jsonify, request

from models import CoinTransaction, FindCheck, WalkPoint, db
from walk_proof import (BLOCK, MAX_POINTS_KEPT, TRAIL_WINDOW_S, as_utc, describe,
                        suspicious_reasons)

walk_proof_api = Blueprint("walk_proof_api", __name__)

KEEP, REVERSE = "keep", "reverse"


def _now():
    return datetime.now(timezone.utc)


def record_point(user_id, lat, lon, when=None):
    """Add one point to this player's trail and forget the old ones. The caller commits."""
    when = when or _now()
    previous = db.session.execute(db.select(WalkPoint.at, WalkPoint.lat, WalkPoint.lon)
                                  .where(WalkPoint.user_id == user_id)
                                  .order_by(WalkPoint.at.desc(), WalkPoint.id.desc()).limit(1)).first()
    from territory_api import record_visit  # claim the campus: colour this hexagon for your team
    record_visit(user_id, lat, lon, when, (as_utc(previous[0]), previous[1], previous[2]) if previous else None)
    db.session.add(WalkPoint(user_id=user_id, lat=lat, lon=lon, at=when))
    too_old = (when - timedelta(seconds=TRAIL_WINDOW_S)).replace(tzinfo=None)
    db.session.execute(db.delete(WalkPoint).where(WalkPoint.user_id == user_id, WalkPoint.at < too_old))
    # Never more than MAX_POINTS_KEPT, even if a phone sends far too often.
    extra = db.session.execute(db.select(WalkPoint.id).where(WalkPoint.user_id == user_id)
                               .order_by(WalkPoint.at.desc(), WalkPoint.id.desc())
                               .offset(MAX_POINTS_KEPT)).scalars().all()
    if extra:
        db.session.execute(db.delete(WalkPoint).where(WalkPoint.id.in_(extra)))


def trail_of(user_id):
    rows = db.session.execute(db.select(WalkPoint.at, WalkPoint.lat, WalkPoint.lon)
                              .where(WalkPoint.user_id == user_id)).all()
    return [tuple(r) for r in rows]


def check_find(user, treasure, lat, lon):
    """Before paying for a find: (message to refuse with, or None; the suspicious reasons).

    In "flag" mode (the default) nothing is refused: the find is paid and flag_find() saves it
    for an admin. In "block" mode a suspicious find is refused with a message.
    """
    now = _now()
    reasons = suspicious_reasons(trail_of(user.id), (lat, lon), (treasure.lat, treasure.lon), now)
    record_point(user.id, lat, lon, now)  # the claim itself is part of your trail too
    db.session.commit()
    if reasons and current_app.config.get("WALK_PROOF") == BLOCK:
        return (f"We couldn't see you walk here: you {describe(reasons)}. "
                "Keep the map open while you walk, then try again."), reasons
    return None, reasons


def flag_find(user_id, treasure_id, reasons):
    """A paid find that looked faked: put it on the admin page. The caller commits."""
    db.session.add(FindCheck(user_id=user_id, treasure_id=treasure_id, reasons=",".join(reasons)))


def _admin():
    from admin_api import _admin_or_error  # here, not at the top: admin_api imports this file
    return _admin_or_error()


@walk_proof_api.route("/api/admin/suspicious-finds")
def suspicious_finds():
    _user, error = _admin()
    if error:
        return error
    rows = db.session.execute(db.select(FindCheck).where(FindCheck.decision.is_(None))
                              .order_by(FindCheck.created_at.desc(), FindCheck.id.desc())).scalars().all()
    return jsonify(finds=[{
        "id": f.id,
        "player": f.user.username,
        "treasure": f.treasure.name,
        "treasure_id": f.treasure_id,
        "why": describe([r for r in f.reasons.split(",") if r]),
        "when": as_utc(f.created_at).isoformat(),
    } for f in rows])


@walk_proof_api.route("/api/admin/suspicious-finds/<int:check_id>", methods=["POST"])
def decide(check_id):
    """{"action": "keep"}: it was fine. {"action": "reverse"}: take the coins back."""
    _user, error = _admin()
    if error:
        return error
    check = db.session.get(FindCheck, check_id)
    if check is None:
        return jsonify(error="No such find"), 404
    if check.decision is not None:
        return jsonify(error="An admin already decided this one"), 409
    action = (request.get_json(silent=True) or {}).get("action")
    if action not in (KEEP, REVERSE):
        return jsonify(error='action must be "keep" or "reverse"'), 400
    if action == REVERSE:
        from coin_api import FOUND_REASON  # (same reason as above)
        # Removing the payment also means the treasure counts as not found: they can find it for real.
        db.session.execute(db.delete(CoinTransaction).where(
            CoinTransaction.user_id == check.user_id, CoinTransaction.treasure_id == check.treasure_id,
            CoinTransaction.reason == FOUND_REASON))
    check.decision = "reversed" if action == REVERSE else "kept"
    check.decided_at = _now()
    db.session.commit()
    return jsonify(id=check.id, decision=check.decision)

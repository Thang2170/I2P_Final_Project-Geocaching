""""Didn't find it" reports (owner: B). The rules live in dnf.py.

    POST /api/treasures/<id>/not-found   {"lat", "lon"}: I looked here and it wasn't there

treasure_api.py adds each treasure's report count and board line to /api/treasures with
report_counts(), so the map can mark "maybe missing" treasures.

app.py registers it like the other Blueprints:

    from dnf_api import dnf_api
    app.register_blueprint(dnf_api)
"""

from flask import Blueprint, jsonify, request

from auth_api import current_user
from dnf import (board_text, is_missing, just_went_missing, open_reporters, problem_text,
                 report_problem, thanks_text)
from live_positions import parse_position
from location import haversine_m
from models import CoinTransaction, MissingAlert, Notification, Treasure, TreasureReport, db
from notify_rules import TREASURE_MISSING

dnf_api = Blueprint("dnf_api", __name__)

FOUND_REASON = "found_treasure"  # the same as coin_api.FOUND_REASON (coin_api imports treasure_api)


def _last_finds():
    """{treasure id: when it was last found}."""
    rows = db.session.execute(db.select(CoinTransaction.treasure_id, db.func.max(CoinTransaction.created_at))
                              .where(CoinTransaction.reason == FOUND_REASON,
                                     CoinTransaction.treasure_id.is_not(None))
                              .group_by(CoinTransaction.treasure_id)).all()
    return dict(rows)


def open_reports():
    """{treasure id: set of players whose report still counts (made after the last find)}."""
    reports = {}
    for tid, uid, when in db.session.execute(db.select(TreasureReport.treasure_id, TreasureReport.user_id,
                                                       TreasureReport.created_at)):
        reports.setdefault(tid, []).append((uid, when))
    last = _last_finds()
    out = {}
    for tid, rows in reports.items():
        who = open_reporters(rows, last.get(tid))
        if who:
            out[tid] = who
    return out


def report_counts():
    """{treasure id: {"count", "missing", "text"}} for every treasure someone reported."""
    return {tid: {"count": len(who), "missing": is_missing(len(who)), "text": board_text(len(who))}
            for tid, who in open_reports().items()}


@dnf_api.route("/api/treasures/<int:treasure_id>/not-found", methods=["POST"])
def report_not_found(treasure_id):
    user = current_user()
    if user is None:
        return jsonify(error="Log in first"), 401
    treasure = db.session.get(Treasure, treasure_id)
    if treasure is None:
        return jsonify(error="No such treasure"), 404
    try:
        lat, lon = parse_position(request.get_json(silent=True))
    except ValueError as err:
        return jsonify(error=str(err)), 400

    before = open_reports().get(treasure.id, set())
    distance_m = haversine_m(lat, lon, treasure.lat, treasure.lon)
    problem = report_problem(treasure.created_by == user.id, distance_m, user.id in before)
    if problem:
        status = 409 if problem == "already" else 400
        return jsonify(error=problem_text(problem, distance_m), problem=problem), status

    db.session.add(TreasureReport(treasure_id=treasure.id, user_id=user.id))
    count = len(before) + 1
    if just_went_missing(len(before), count):
        note = None
        if treasure.created_by is not None:  # the built-in treasure has no owner to tell
            note = Notification(user_id=treasure.created_by, kind=TREASURE_MISSING)
            db.session.add(note)
            db.session.flush()
        db.session.add(MissingAlert(treasure_id=treasure.id, count=count,
                                    notification_id=note.id if note else None))
    db.session.commit()
    return jsonify(count=count, missing=is_missing(count), text=board_text(count),
                   thanks=thanks_text(count)), 201

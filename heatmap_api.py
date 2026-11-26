"""Campus heat map (owner: B). The rules live in heatmap.py.

    GET /heatmap                 the page
    GET /api/heatmap?days=30     the busy hexagons (only those with 5+ different players)

record_heat() is called by walk_proof_api.record_point() every time the map sends a position.

app.py registers it like the other Blueprints:

    from heatmap_api import heatmap_api
    app.register_blueprint(heatmap_api)
"""

from datetime import datetime, timedelta, timezone

from flask import Blueprint, jsonify, redirect, render_template, request

from auth_api import current_user
from heatmap import (DAY_CHOICES, KEEP_DAYS, MIN_PLAYERS, heat_cells, legend, parse_days,
                     place_text, summary_text, tip_text)
from location import haversine_m
from models import HeatVisit, Treasure, db
from streaks import local_day
from territory import ORIGIN, hex_of
from walk_proof import teleports

heatmap_api = Blueprint("heatmap_api", __name__)

NEAR_TREASURE_M = 80  # a hexagon's tooltip names a treasure this close to its centre


def _now():
    return datetime.now(timezone.utc)


def record_heat(user_id, lat, lon, when, previous=None):
    """Count this player in this hexagon today (once a day). The caller commits.

    previous: the last (when, lat, lon) point. A teleport from it doesn't count, the same
    rule as the territory game. Your visits older than KEEP_DAYS are deleted here too.
    """
    day = local_day(when)
    db.session.execute(db.delete(HeatVisit).where(HeatVisit.user_id == user_id,
                                                  HeatVisit.day < day - timedelta(days=KEEP_DAYS)))
    if previous is not None and teleports([previous, (when, lat, lon)]):
        return False
    q, r = hex_of(lat, lon)
    if db.session.execute(db.select(HeatVisit.id).where(HeatVisit.user_id == user_id, HeatVisit.day == day,
                                                        HeatVisit.q == q, HeatVisit.r == r)).first():
        return False
    db.session.add(HeatVisit(user_id=user_id, q=q, r=r, day=day))
    return True


def _nearest_treasure(centre, treasures):
    best = None
    for t in treasures:
        d = haversine_m(centre[0], centre[1], t.lat, t.lon)
        if d <= NEAR_TREASURE_M and (best is None or d < best[0]):
            best = (d, t.name)
    return best[1] if best else None


def heat_report(days, today=None):
    today = today or local_day(_now())
    since = today - timedelta(days=days - 1)
    visits = db.session.execute(db.select(HeatVisit.user_id, HeatVisit.q, HeatVisit.r)
                                .where(HeatVisit.day >= since, HeatVisit.day <= today)).all()
    cells = heat_cells(visits)
    shown = {(c["q"], c["r"]) for c in cells}
    hidden = len({(q, r) for _, q, r in visits} - shown)
    treasures = db.session.execute(db.select(Treasure)).scalars().all()
    for cell in cells:
        nearest = _nearest_treasure(cell["centre"], treasures)
        cell["tip"] = tip_text(cell, days, nearest)
        cell["place"] = place_text(nearest)
    return {"days": days, "day_choices": list(DAY_CHOICES), "min_players": MIN_PLAYERS,
            "cells": cells, "legend": legend(), "summary": summary_text(cells, days, hidden),
            "centre": list(ORIGIN)}


@heatmap_api.route("/heatmap")
def heatmap_page():
    if current_user() is None:
        return redirect("/login?next=/heatmap")
    return render_template("heatmap.html")


@heatmap_api.route("/api/heatmap")
def api_heatmap():
    if current_user() is None:
        return jsonify(error="Log in first"), 401
    try:
        days = parse_days(request.args.get("days"))
    except ValueError as err:
        return jsonify(error=str(err)), 400
    return jsonify(heat_report(days))

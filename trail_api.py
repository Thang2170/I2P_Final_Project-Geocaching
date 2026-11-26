"""Treasure Trail: POST /api/trail plans a walking loop for a step or time goal (owner: B).

The rules and the algorithm live in trail_planner.py. This file only reads the request,
picks the treasures you can still find, and asks routing.get_route (A's file, unchanged)
for the real walking path of the loop.
"""

import json
from datetime import datetime, timezone

from flask import Blueprint, jsonify, render_template, request

from auth_api import current_user
from calculator import steps_from_distance
from coin_api import found_treasure_ids
from journey_log import speed_problem
from location import haversine_m
from models import ActiveTrail, Post, TrailWalk, TrailWalkDetail, Treasure, TreasureRating, db
from walk_api import _saved_weight, energy_for
from walk_input import DEFAULT_WEIGHT_KG, parse_distance_m, parse_duration_s
from routing import get_route
from location import FOUND_RADIUS_M
from trail_planner import (SHAPES, best_change, best_text, can_carry_on, fmt_duration, low_rated, pace_text,
                           parse_active_trail, parse_goal, parse_shape, plan_trail, splits_text, trail_post_text,
                           trail_progress, trail_signature)
from weather_api import public_choice, weather_for
from treasure_input import parse_number

trail_api = Blueprint("trail_api", __name__)


@trail_api.route("/api/trail", methods=["POST"])
def make_trail():
    """Send JSON: lat, lon (where you are) and steps OR minutes.
    B: optional shape ("loop", the default, or "oneway") and skip_low (true: leave out treasures
    other players rated 2 stars or less on average).

    Answers with the stops in walking order and the real walking path of the whole trail.
    """
    user = current_user()
    if user is None:
        return jsonify(error="Log in first"), 401
    data = request.get_json(silent=True) or {}
    try:
        lat = parse_number(data.get("lat"), "lat", -90, 90)
        lon = parse_number(data.get("lon"), "lon", -180, 180)
        budget_m, label = parse_goal(data)
        shape = parse_shape(data.get("shape"))
        skip_low = data.get("skip_low", False)
        if not isinstance(skip_low, bool):
            raise ValueError("skip_low must be true or false")
    except ValueError as err:
        return jsonify(error=str(err)), 400
    loop = shape == "loop"

    # Only treasures you can still earn coins from: not found yet, and not your own.
    found = set(found_treasure_ids(user.id))
    treasures = [t for t in db.session.execute(db.select(Treasure)).scalars()
                 if t.id not in found and t.created_by != user.id]
    from condition_api import hidden_ids  # B: no rain / night treasure that isn't out now
    hidden = hidden_ids(treasures, user.id)
    treasures = [t for t in treasures if t.id not in hidden]
    skipped = 0
    if skip_low:  # B: leave out treasures other players didn't enjoy
        ratings = {}
        for tid, stars in db.session.execute(db.select(TreasureRating.treasure_id, TreasureRating.stars)):
            ratings.setdefault(tid, []).append(stars)
        low = low_rated(ratings)
        skipped = sum(1 for t in treasures if t.id in low)
        treasures = [t for t in treasures if t.id not in low]
    plan = plan_trail((lat, lon), [{"id": t.id, "lat": t.lat, "lon": t.lon} for t in treasures], budget_m,
                      loop=loop)
    if not plan["ids"]:
        return jsonify(goal=label, stops=[], message=(
            "No treasure you haven't found fits in that walk. Try a longer one.")), 200

    by_id = {t.id: t for t in treasures}
    stops = [by_id[i] for i in plan["ids"]]
    weather, choice = weather_for(lat, lon)  # B: shortest in the rain, greener in the heat
    back = [(lat, lon)] if loop else []  # B: a one-way trail ends at the last treasure
    from route_access_api import route_settings  # B: step-free routes (route_access.py)
    _, profile, extra = route_settings(user, choice["route_options"])
    route = get_route([(lat, lon), *[(t.lat, t.lon) for t in stops], *back], extra=extra, profile=profile)
    return jsonify(
        goal=label,
        stops=[{"order": n, "id": t.id, "name": t.name, "lat": t.lat, "lon": t.lon}
               for n, t in enumerate(stops, start=1)],
        path=route["path"],
        distance_m=route["distance_m"],
        duration_s=route["duration_s"],
        steps=steps_from_distance(route["distance_m"]),
        warning=route.get("warning"),
        weather=public_choice(choice) if weather else None,
        message=_message(len(stops), len(treasures), label, shape, skipped),
        start=[lat, lon],  # B: a loop's last checkpoint is back here
        shape=shape,
    )


@trail_api.route("/api/trail/progress", methods=["POST"])
def progress():
    """B: walking a trail one leg at a time. Python decides when you reached a checkpoint.

    Send JSON: lat, lon (where you are), checkpoints ([[lat, lon], ...] in order, the last one
    back at the start) and index (the checkpoint you were heading to).
    """
    data = request.get_json(silent=True) or {}
    try:
        lat = parse_number(data.get("lat"), "lat", -90, 90)
        lon = parse_number(data.get("lon"), "lon", -180, 180)
        raw = data.get("checkpoints")
        if not isinstance(raw, list) or not 1 <= len(raw) <= 20:
            raise ValueError("checkpoints must be a list of 1 to 20 [lat, lon] points")
        checkpoints = [(parse_number(p[0], "lat", -90, 90), parse_number(p[1], "lon", -180, 180))
                       for p in raw if isinstance(p, (list, tuple)) and len(p) == 2]
        if len(checkpoints) != len(raw):
            raise ValueError("each checkpoint must be [lat, lon]")
        index = data.get("index")
        if not isinstance(index, int) or isinstance(index, bool):
            raise ValueError("index must be a whole number")
        return jsonify(trail_progress((lat, lon), checkpoints, index, FOUND_RADIUS_M))
    except ValueError as err:
        return jsonify(error=str(err)), 400


def _message(n_stops, n_left, label, shape="loop", skipped=0):
    """What the map says above the stops. If every treasure you can still find is already on the
    trail, the walk is shorter than your goal: say why, so it doesn't look like a mistake."""
    kind = SHAPES[shape]
    text = f"{n_stops} treasure{'s' if n_stops != 1 else ''} on your {label} {kind}."
    if n_stops == n_left:
        text += f" That's every treasure you haven't found yet, so the {kind} is shorter than your goal."
    if skipped:
        text += f" Skipped {skipped} low-rated treasure{'s' if skipped != 1 else ''}."
    return text


MAX_SPLITS = 20


@trail_api.route("/api/trail/walks", methods=["POST"])
def save_trail_walk():
    """B: save a trail walked with the live panel, and post it to the Community.

    Send JSON: distance_m, duration_s, lat, lon (where you finished), end ([lat, lon], the last
    checkpoint: back at the start for a loop; "start" is accepted too), shape ("loop" or "oneway"),
    checkpoints (how many) and splits (seconds at each checkpoint, optional).
    Python checks you are at the end and that the speed is a walk or a run, and works out
    the steps and calories itself.
    """
    user = current_user()
    if user is None:
        return jsonify(error="Log in first"), 401
    data = request.get_json(silent=True) or {}
    try:
        distance_m = parse_distance_m(data.get("distance_m"))
        duration_s = int(parse_duration_s(data.get("duration_s")))
        lat = parse_number(data.get("lat"), "lat", -90, 90)
        lon = parse_number(data.get("lon"), "lon", -180, 180)
        end = data.get("end", data.get("start"))
        if not isinstance(end, list) or len(end) != 2:
            raise ValueError("end must be [lat, lon]")
        end = (parse_number(end[0], "lat", -90, 90), parse_number(end[1], "lon", -180, 180))
        shape = parse_shape(data.get("shape"))
        checkpoints = data.get("checkpoints")
        if not isinstance(checkpoints, int) or isinstance(checkpoints, bool) or not 1 <= checkpoints <= 20:
            raise ValueError("checkpoints must be a whole number from 1 to 20")
        splits = data.get("splits") or []
        if not isinstance(splits, list) or len(splits) > MAX_SPLITS:
            raise ValueError(f"splits must be a list of at most {MAX_SPLITS} times")
        splits = [int(parse_number(x, "split", 0, duration_s)) for x in splits]
        if splits != sorted(splits):
            raise ValueError("splits must go up")
        treasure_ids = data.get("treasure_ids") or []  # B: which treasures, for personal bests
        if (not isinstance(treasure_ids, list) or len(treasure_ids) > MAX_SPLITS
                or not all(isinstance(i, int) and not isinstance(i, bool) and i > 0 for i in treasure_ids)):
            raise ValueError(f"treasure_ids must be a list of at most {MAX_SPLITS} ids")
    except ValueError as err:
        return jsonify(error=str(err)), 400

    away = haversine_m(lat, lon, end[0], end[1])
    if away > FOUND_RADIUS_M:
        where = "the start. A loop ends back where it began" if shape == "loop" else "the last checkpoint"
        return jsonify(error=f"You are {round(away)} m from {where}."), 400
    problem = speed_problem(distance_m, duration_s)
    if problem:
        return jsonify(error=problem), 400

    weight_kg = _saved_weight(user) or DEFAULT_WEIGHT_KG
    energy = energy_for(user, distance_m, weight_kg, duration_s)
    # B: your best time on this same trail so far, if you walked it before
    signature = trail_signature(shape, treasure_ids)
    previous = None
    if signature:
        previous = db.session.execute(
            db.select(db.func.min(TrailWalk.duration_s))
            .join(TrailWalkDetail, TrailWalkDetail.walk_id == TrailWalk.id)
            .where(TrailWalk.user_id == user.id, TrailWalkDetail.signature == signature)).scalar()
    change = best_change(previous, duration_s) if signature else None
    text = trail_post_text(checkpoints, distance_m, duration_s, energy["steps"], energy["calories"], splits, shape)
    if change:
        text += best_text(change)
    post = Post(user_id=user.id, text=text)
    db.session.add(post)
    db.session.flush()
    walk = TrailWalk(user_id=user.id, checkpoints=checkpoints, distance_m=distance_m, duration_s=duration_s,
                     steps=energy["steps"], calories=energy["calories"], post_id=post.id)
    db.session.add(walk)
    db.session.flush()
    db.session.add(TrailWalkDetail(walk_id=walk.id, signature=signature, shape=shape,
                                   treasure_ids=json.dumps(treasure_ids), splits=json.dumps(splits)))
    db.session.commit()
    return jsonify(id=walk.id, post_id=post.id, text=text, steps=walk.steps, calories=walk.calories,
                   distance_m=walk.distance_m, duration_s=walk.duration_s, best=change), 201


# ---------------------------------------------------------------- B: trail history and personal bests

HISTORY_SIZE = 50


@trail_api.route("/trails")
def trails_page():
    return render_template("trails.html")


@trail_api.route("/api/trail/walks", methods=["GET"])
def my_trail_walks():
    """Your saved trails, newest first, with pace, splits and personal bests (🏅)."""
    user = current_user()
    if user is None:
        return jsonify(error="Log in first"), 401
    rows = db.session.execute(
        db.select(TrailWalk, TrailWalkDetail)
        .outerjoin(TrailWalkDetail, TrailWalkDetail.walk_id == TrailWalk.id)
        .where(TrailWalk.user_id == user.id)
        .order_by(TrailWalk.created_at.desc(), TrailWalk.id.desc())).all()
    # best time and number of walks for each trail (over all your walks, not only the ones shown)
    best, count = {}, {}
    for walk, detail in rows:
        sig = detail.signature if detail else None
        if sig:
            count[sig] = count.get(sig, 0) + 1
            if sig not in best or walk.duration_s < best[sig][0] or (
                    walk.duration_s == best[sig][0] and walk.id < best[sig][1]):
                best[sig] = (walk.duration_s, walk.id)  # a tie goes to the earlier walk
    ids = {i for _, d in rows[:HISTORY_SIZE] if d for i in json.loads(d.treasure_ids)}
    names = dict(db.session.execute(db.select(Treasure.id, Treasure.name).where(Treasure.id.in_(ids))).all()) if ids else {}
    walks = []
    for walk, detail in rows[:HISTORY_SIZE]:
        sig = detail.signature if detail else None
        splits = json.loads(detail.splits) if detail else []
        walks.append({
            "id": walk.id,
            "at": _utc(walk.created_at).isoformat(),
            "shape": detail.shape if detail else "loop",
            "checkpoints": walk.checkpoints,
            "treasures": [names.get(i, "a removed treasure") for i in json.loads(detail.treasure_ids)] if detail else [],
            "distance_m": round(walk.distance_m),
            "duration": fmt_duration(walk.duration_s),
            "pace": pace_text(walk.distance_m, walk.duration_s),
            "steps": walk.steps,
            "calories": round(walk.calories),
            "splits": splits_text(splits),
            "personal_best": bool(sig) and best[sig][1] == walk.id and count[sig] > 1,
            "times_walked": count.get(sig, 1),
            "best": fmt_duration(best[sig][0]) if sig else None,
            "post_id": walk.post_id,
        })
    totals = {"walks": len(rows), "distance_m": round(sum(w.distance_m for w, _ in rows)),
              "steps": sum(w.steps for w, _ in rows)}
    return jsonify(walks=walks, totals=totals)


# ---------------------------------------------------------------- B: carry on a trail after a reload

def _utc(when):
    return when if when.tzinfo else when.replace(tzinfo=timezone.utc)  # SQLite drops the zone


@trail_api.route("/api/trail/active", methods=["POST"])
def keep_active_trail():
    """Keep the timed trail you are walking (start, each checkpoint, and every 30 s)."""
    user = current_user()
    if user is None:
        return jsonify(error="Log in first"), 401
    try:
        state = parse_active_trail(request.get_json(silent=True))
    except ValueError as err:
        return jsonify(error=str(err)), 400
    row = db.session.get(ActiveTrail, user.id) or ActiveTrail(user_id=user.id)
    row.state = json.dumps(state)
    row.updated_at = datetime.now(timezone.utc)
    db.session.add(row)
    db.session.commit()
    return jsonify(ok=True)


@trail_api.route("/api/trail/active", methods=["GET"])
def get_active_trail():
    """The trail to carry on after a reload, or {"active": null}. A stale one is forgotten."""
    user = current_user()
    if user is None:
        return jsonify(error="Log in first"), 401
    row = db.session.get(ActiveTrail, user.id)
    if row is None:
        return jsonify(active=None)
    since = int((datetime.now(timezone.utc) - _utc(row.updated_at)).total_seconds())
    if not can_carry_on(since):
        db.session.delete(row)
        db.session.commit()
        return jsonify(active=None, expired=True)
    return jsonify(active=json.loads(row.state) | {"since_update_s": since})


@trail_api.route("/api/trail/active", methods=["DELETE"])
def end_active_trail():
    """Finished, saved or stopped: nothing to carry on."""
    user = current_user()
    if user is None:
        return jsonify(error="Log in first"), 401
    row = db.session.get(ActiveTrail, user.id)
    if row:
        db.session.delete(row)
        db.session.commit()
    return jsonify(ok=True)


@trail_api.route("/api/trail/walks/<int:walk_id>/again")
def walk_again(walk_id):
    """B: set up one of your saved trails again: the same treasures in the same order, from where
    you are now (lat, lon), so you can try to beat your time. Treasures you already found don't
    pay again (coin_api refuses a second find)."""
    user = current_user()
    if user is None:
        return jsonify(error="Log in first"), 401
    try:
        lat = parse_number(request.args.get("lat"), "lat", -90, 90)
        lon = parse_number(request.args.get("lon"), "lon", -180, 180)
    except ValueError as err:
        return jsonify(error=str(err)), 400
    walk = db.session.get(TrailWalk, walk_id)
    detail = db.session.get(TrailWalkDetail, walk_id)
    if walk is None or walk.user_id != user.id:
        return jsonify(error="That trail was not found"), 404
    ids = json.loads(detail.treasure_ids) if detail else []
    by_id = {t.id: t for t in db.session.execute(db.select(Treasure).where(Treasure.id.in_(ids))).scalars()} if ids else {}
    stops = [by_id[i] for i in ids if i in by_id]
    if not stops:
        return jsonify(error="This trail can't be walked again: its treasures were removed."), 400
    missing = len(ids) - len(stops)
    message = f"Walk it again and beat your best time: {len(stops)} checkpoint{'s' if len(stops) != 1 else ''}."
    if missing:
        message += (f" {missing} treasure{'s were' if missing != 1 else ' was'} removed, "
                    "so this one won't count as the same trail.")
    return jsonify(
        shape=detail.shape,
        stops=[{"order": n, "id": t.id, "name": t.name, "lat": t.lat, "lon": t.lon} for n, t in enumerate(stops, start=1)],
        start=[lat, lon],
        message=message,
    )

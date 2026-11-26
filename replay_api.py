"""Hunt replay (owner: B). The rules live in replay.py.

    GET /hunts/<id>/replay          the replay page (a map that plays the race back)
    GET /api/hunts/<id>/replay      the race as data: each player's path, the winner, the speed
    GET /hunts/demo-replay          the demo race's replay (presenter mode jumps here)

record_race_point() is called by /api/me/position (admin_api.py) every time the map sends
where you are: while you are racing in a hunt, the point is also kept for the replay.

app.py registers it like the other Blueprints:

    from replay_api import replay_api
    app.register_blueprint(replay_api)
"""

from datetime import datetime, timezone

from flask import Blueprint, jsonify, redirect, render_template

from auth_api import current_user
from hunt_game_api import HuntGame, member_ids
from models import Hunt, RacePoint, Treasure, User, db
from queue_logic import PLAYING, queue_status
from replay import build_replay, replay_problem, should_keep

replay_api = Blueprint("replay_api", __name__)

DEMO_RACE_NAME = "Pond sprint (demo)"  # the same as demo_content.DEMO_RACE["name"]


def _naive_utc(when):
    return when.astimezone(timezone.utc).replace(tzinfo=None) if when.tzinfo else when


def record_race_point(user_id, lat, lon, when=None):
    """Keep this position for every race the player is running now. The caller commits."""
    when = _naive_utc(when or datetime.now(timezone.utc))
    racing = db.session.execute(
        db.select(HuntGame.hunt_id, Hunt.capacity)
        .join(Hunt, Hunt.id == HuntGame.hunt_id)
        .where(HuntGame.started_at.is_not(None), HuntGame.winner_id.is_(None))).all()
    for hunt_id, capacity in racing:
        ids = member_ids(hunt_id)
        status = queue_status(user_id, ids, capacity) if user_id in ids else None
        if status is None or status["state"] != PLAYING:
            continue
        last, kept = db.session.execute(
            db.select(db.func.max(RacePoint.at), db.func.count(RacePoint.id))
            .where(RacePoint.hunt_id == hunt_id, RacePoint.user_id == user_id)).one()
        if should_keep(last, when, kept):
            db.session.add(RacePoint(hunt_id=hunt_id, user_id=user_id, lat=lat, lon=lon, at=when))


def replay_data(hunt):
    game = db.session.get(HuntGame, hunt.id)
    treasure = db.session.get(Treasure, game.treasure_id)
    winner = db.session.get(User, game.winner_id) if game.winner_id else None
    paths = {}
    rows = db.session.execute(db.select(User.username, RacePoint.at, RacePoint.lat, RacePoint.lon)
                              .join(User, User.id == RacePoint.user_id)
                              .where(RacePoint.hunt_id == hunt.id)).all()
    for name, when, lat, lon in rows:
        paths.setdefault(name, []).append((when, lat, lon))
    # A hunt won before this feature has no finish time saved: end at the last point.
    end = game.finished_at or max((p[0] for pts in paths.values() for p in pts), default=game.started_at)
    data = build_replay(_naive_utc(game.started_at), _naive_utc(end), paths,
                        winner.username if winner else None,
                        {"name": treasure.name, "lat": treasure.lat, "lon": treasure.lon})
    data["hunt"] = {"id": hunt.id, "name": hunt.name}
    return data


def _check(hunt_id):
    """(hunt, None) or (None, error response)."""
    user = current_user()
    if user is None:
        return None, (jsonify(error="Log in first"), 401)
    hunt = db.session.get(Hunt, hunt_id)
    if hunt is None:
        return None, (jsonify(error="No such hunt"), 404)
    game = db.session.get(HuntGame, hunt.id)
    finished = game is not None and game.winner_id is not None and game.started_at is not None
    is_member = user.id in member_ids(hunt.id)
    problem = replay_problem(finished, is_member)
    if problem:
        return None, (jsonify(error=problem), 409 if is_member else 403)
    return hunt, None


@replay_api.route("/api/hunts/<int:hunt_id>/replay")
def api_replay(hunt_id):
    hunt, error = _check(hunt_id)
    if error:
        return error
    return jsonify(replay_data(hunt))


@replay_api.route("/hunts/<int:hunt_id>/replay")
def replay_page(hunt_id):
    if current_user() is None:
        return redirect(f"/login?next=/hunts/{hunt_id}/replay")
    hunt = db.session.get(Hunt, hunt_id)
    if hunt is None:
        return "No such hunt", 404
    return render_template("replay.html", hunt_id=hunt.id, hunt_name=hunt.name)


@replay_api.route("/hunts/demo-replay")
def demo_replay():
    hunt_id = db.session.execute(db.select(Hunt.id).where(Hunt.name == DEMO_RACE_NAME)).scalar()
    if hunt_id is None:
        return redirect("/hunts")
    return redirect(f"/hunts/{hunt_id}/replay")

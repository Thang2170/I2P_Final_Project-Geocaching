"""Ghost racing (owner: B). Rules: ghost.py. The ghosts come from finished hunt races (replay_api.py).

- GET  /ghost                               the page
- GET  /api/ghosts                          treasures that have a ghost to race
- GET  /api/ghosts/<treasure_id>?who=me     the ghost's path (who=me: your own best win there)
- POST /api/ghosts/<treasure_id>/compare    {"elapsed_s", "lat", "lon", "who"}: where the ghost is, who leads
"""

from flask import Blueprint, jsonify, redirect, render_template, request

from auth_api import current_user
from ghost import compare, fastest, ghost_path
from hunt_game_api import HuntGame
from models import RacePoint, Treasure, User, db
from play_input import parse_position, parse_seconds
from replay import clock

ghost_api = Blueprint("ghost_api", __name__)


def _runs(treasure, winner_id=None):
    """Every won race to this treasure as (winner name, seconds, path)."""
    query = (db.select(HuntGame, User.username).join(User, User.id == HuntGame.winner_id)
             .where(HuntGame.treasure_id == treasure.id, HuntGame.started_at.is_not(None)))
    if winner_id is not None:
        query = query.where(HuntGame.winner_id == winner_id)
    runs = []
    for game, name in db.session.execute(query).all():
        points = db.session.execute(db.select(RacePoint.at, RacePoint.lat, RacePoint.lon).where(
            RacePoint.hunt_id == game.hunt_id, RacePoint.user_id == game.winner_id)).all()
        end = game.finished_at or max((p[0] for p in points), default=None)
        if not points or end is None or end <= game.started_at:
            continue
        path = ghost_path(game.started_at, end, [tuple(p) for p in points], (treasure.lat, treasure.lon))
        runs.append((name, path[-1][0], path))
    return runs


def _ghost(treasure_id, me, who):
    """(treasure, run) or (None, error response)."""
    treasure = db.session.get(Treasure, treasure_id)
    if treasure is None:
        return None, (jsonify(error="No such treasure"), 404)
    run = fastest(_runs(treasure, me.id if who == "me" else None))
    if run is None:
        text = "You have not won a race to this treasure yet." if who == "me" else "Nobody has raced to this treasure yet."
        return None, (jsonify(error=text), 404)
    return treasure, run


@ghost_api.route("/ghost")
def ghost_page():
    if current_user() is None:
        return redirect("/login?next=/ghost")
    return render_template("ghost.html")


@ghost_api.route("/api/ghosts")
def list_ghosts():
    me = current_user()
    if me is None:
        return jsonify(error="Log in first"), 401
    ghosts = []
    for treasure in db.session.execute(db.select(Treasure).order_by(Treasure.name)).scalars():
        runs = _runs(treasure)
        best = fastest(runs)
        if best is None:
            continue
        mine = fastest([r for r in runs if r[0] == me.username])
        ghosts.append({"treasure_id": treasure.id, "treasure": treasure.name, "ghost": best[0],
                       "time": clock(best[1]), "my_best": clock(mine[1]) if mine else None})
    return jsonify(ghosts=ghosts)


@ghost_api.route("/api/ghosts/<int:treasure_id>")
def get_ghost(treasure_id):
    me = current_user()
    if me is None:
        return jsonify(error="Log in first"), 401
    treasure, run = _ghost(treasure_id, me, request.args.get("who"))
    if treasure is None:
        return run
    name, seconds, path = run
    return jsonify(treasure={"id": treasure.id, "name": treasure.name, "lat": treasure.lat, "lon": treasure.lon},
                   ghost=name, duration_s=seconds, time=clock(seconds),
                   start={"lat": path[0][1], "lon": path[0][2]},
                   line=[[lat, lon] for _, lat, lon in path])


@ghost_api.route("/api/ghosts/<int:treasure_id>/compare", methods=["POST"])
def compare_api(treasure_id):
    me = current_user()
    if me is None:
        return jsonify(error="Log in first"), 401
    data = request.get_json(silent=True)
    try:
        lat, lon = parse_position(data)
        elapsed = parse_seconds(data.get("elapsed_s"))
    except ValueError as err:
        return jsonify(error=str(err)), 400
    treasure, run = _ghost(treasure_id, me, data.get("who"))
    if treasure is None:
        return run
    name, _, path = run
    return jsonify(compare(path, name, elapsed, lat, lon, (treasure.lat, treasure.lon)) | {"ghost_name": name})

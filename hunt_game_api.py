"""Hunt races (owner: A): start a hunt, see where it goes, and win it.

Rules live in hunt_game.py. The race is saved in its own small table (hunt_games)
instead of new columns on "hunts": db.create_all() adds a NEW table to an existing
geohunt.db, but it never adds columns to an old table, so this keeps everyone's
database working without deleting it.

app.py registers it like the other Blueprints:

    from hunt_game_api import hunt_game_api
    app.register_blueprint(hunt_game_api)
"""

from datetime import datetime, timezone

from flask import Blueprint, jsonify, request

from admin_api import live_players
from auth_api import current_user
from coin_api import get_balance
from hunt_game import (FINISHED, OPEN, WIN_BONUS, WIN_REASON, game_state, start_problem,
                       win_problem)
from live_positions import parse_position
from location import haversine_m
from models import CoinTransaction, Hunt, HuntMember, Treasure, User, db
from notify_api import notify
from notify_rules import HUNT_WON
from queue_logic import PLAYING, queue_status

hunt_game_api = Blueprint("hunt_game_api", __name__)


class HuntGame(db.Model):
    """The race of one hunt: where it goes, when it started, and who won."""

    __tablename__ = "hunt_games"
    hunt_id = db.Column(db.Integer, db.ForeignKey("hunts.id"), primary_key=True)
    treasure_id = db.Column(db.Integer, db.ForeignKey("treasures.id"), nullable=False)
    started_at = db.Column(db.DateTime, nullable=True)
    winner_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    finished_at = db.Column(db.DateTime, nullable=True)


# ------------------------------------------------------------ helpers (also used by hunt_api.py)


def oldest_treasure_id():
    """The first treasure (the NTHU demo one): the default destination."""
    return db.session.execute(db.select(Treasure.id).order_by(Treasure.id).limit(1)).scalar()


def parse_treasure_id(value):
    """The treasure a new hunt goes to. Empty means the default one. Raises ValueError."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return oldest_treasure_id()
    try:
        treasure_id = int(value)
    except (TypeError, ValueError):
        raise ValueError("Pick a treasure from the list") from None
    if db.session.get(Treasure, treasure_id) is None:
        raise ValueError("That treasure doesn't exist")
    return treasure_id


def get_game(hunt_id):
    """The hunt's game, made on first use. Hunts from before this feature (and the
    demo hunts) get the first treasure, so every hunt has somewhere to go."""
    game = db.session.get(HuntGame, hunt_id)
    if game is None:
        treasure_id = oldest_treasure_id()
        if treasure_id is None:
            return None  # no treasures at all yet
        game = HuntGame(hunt_id=hunt_id, treasure_id=treasure_id)
        db.session.add(game)
        db.session.flush()
    return game


def member_ids(hunt_id):
    """Everyone in the hunt, in the order they joined (same order as hunt_api.py)."""
    query = db.select(HuntMember.user_id).where(HuntMember.hunt_id == hunt_id).order_by(HuntMember.id)
    return db.session.execute(query).scalars().all()


def _is_playing(user, hunt, ids):
    status = queue_status(user.id, ids, hunt.capacity) if user else None
    return status is not None and status["state"] == PLAYING


def game_dict(hunt, user):
    """What the Hunts page and the map need to know about the race."""
    game = get_game(hunt.id)
    if game is None:
        return {"state": OPEN, "treasure": None, "winner": None, "can_start": False}
    state = game_state(game.started_at, game.winner_id)
    treasure = db.session.get(Treasure, game.treasure_id)
    winner = db.session.get(User, game.winner_id) if game.winner_id else None
    can_start = user is not None and start_problem(
        user.id, hunt.created_by, _is_playing(user, hunt, member_ids(hunt.id)), state) is None
    return {
        "state": state,
        "treasure": {"id": treasure.id, "name": treasure.name, "lat": treasure.lat, "lon": treasure.lon},
        "winner": winner.username if winner else None,
        "can_start": can_start,
    }


def game_state_of(hunt_id):
    """open / started / finished, for hunt_api.py's join check."""
    game = get_game(hunt_id)
    return game_state(game.started_at, game.winner_id) if game else OPEN


def _find_hunt():
    """(user, hunt) for a request, or an error response."""
    user = current_user()
    if user is None:
        return None, None, (jsonify(error="Log in first"), 401)
    hunt = db.session.get(Hunt, request.view_args["hunt_id"])
    if hunt is None:
        return None, None, (jsonify(error="No such hunt"), 404)
    return user, hunt, None


# ------------------------------------------------------------ endpoints


@hunt_game_api.route("/api/hunts/<int:hunt_id>/game")
def show_game(hunt_id):
    """GET: the hunt's name, its treasure, the state and the winner."""
    user, hunt, error = _find_hunt()
    if error:
        return error
    data = game_dict(hunt, user)
    db.session.commit()  # get_game may have just made the row
    return jsonify(hunt_id=hunt.id, name=hunt.name, **data)


@hunt_game_api.route("/api/hunts/<int:hunt_id>/start", methods=["POST"])
def start_game(hunt_id):
    """POST: start the race. The creator only (any playing member for the demo hunts)."""
    user, hunt, error = _find_hunt()
    if error:
        return error
    game = get_game(hunt.id)
    if game is None:
        return jsonify(error="There are no treasures yet, so the hunt has nowhere to go."), 409
    state = game_state(game.started_at, game.winner_id)
    problem = start_problem(user.id, hunt.created_by, _is_playing(user, hunt, member_ids(hunt.id)), state)
    if problem:
        return jsonify(error=problem), 409
    game.started_at = datetime.now(timezone.utc)
    db.session.commit()
    return jsonify(hunt_id=hunt.id, name=hunt.name, **game_dict(hunt, user))


@hunt_game_api.route("/api/hunts/<int:hunt_id>/arrived", methods=["POST"])
def arrived(hunt_id):
    """POST {"lat", "lon"}: the map says you reached the treasure. The first one wins."""
    user, hunt, error = _find_hunt()
    if error:
        return error
    try:
        lat, lon = parse_position(request.get_json(silent=True))
    except ValueError as err:
        return jsonify(error=str(err)), 400
    game = get_game(hunt.id)
    if game is None:
        return jsonify(error="This hunt has no treasure."), 409
    treasure = db.session.get(Treasure, game.treasure_id)
    distance_m = haversine_m(lat, lon, treasure.lat, treasure.lon)
    ids = member_ids(hunt.id)
    problem = win_problem(game_state(game.started_at, game.winner_id),
                          _is_playing(user, hunt, ids), distance_m)
    if problem:
        return jsonify(error=problem, name=hunt.name, **game_dict(hunt, user)), 409

    # Two players can arrive at the same moment. This UPDATE only works while there is
    # no winner yet, so exactly one of them wins (the database decides, not the timing).
    won = db.session.execute(
        db.update(HuntGame)
        .where(HuntGame.hunt_id == hunt.id, HuntGame.winner_id.is_(None))
        .values(winner_id=user.id, finished_at=datetime.now(timezone.utc))
    ).rowcount == 1
    if not won:
        db.session.rollback()
        return jsonify(error="Someone got there just before you.", name=hunt.name, **game_dict(hunt, user)), 409

    db.session.add(CoinTransaction(user_id=user.id, amount=WIN_BONUS, reason=WIN_REASON))
    for member_id in ids:
        notify(member_id, HUNT_WON, actor_id=user.id, hunt_id=hunt.id)  # skips the winner
    db.session.commit()
    db.session.expire_all()
    return jsonify(won=True, bonus=WIN_BONUS, balance=get_balance(user.id),
                   hunt_id=hunt.id, name=hunt.name, **game_dict(hunt, user))


@hunt_game_api.route("/api/hunts/<int:hunt_id>/players")
def teammates(hunt_id):
    """GET: where the OTHER players of this hunt are (the hunt map draws them).

    Only for players who are playing in this hunt (not the waiting line, not outsiders),
    and only positions from the last 2 minutes, like the admin map.
    """
    user, hunt, error = _find_hunt()
    if error:
        return error
    ids = member_ids(hunt.id)
    if not _is_playing(user, hunt, ids):
        return jsonify(error="Only players in this hunt can see each other."), 403
    playing = [uid for uid in ids if queue_status(uid, ids, hunt.capacity)["state"] == PLAYING]
    others = [uid for uid in playing if uid != user.id]
    return jsonify(players=live_players(datetime.now(timezone.utc), user_ids=others))

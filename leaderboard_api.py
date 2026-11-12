"""Leaderboard: the players with the most coins (owner: A). Ranking lives in leaderboard.py.

Like route_api.py, this lives in its own Blueprint. app.py only needs:

    from leaderboard_api import leaderboard_api
    app.register_blueprint(leaderboard_api)
"""

from flask import Blueprint, jsonify, render_template
from sqlalchemy import func

from coin_api import FOUND_REASON
from leaderboard import rank_players
from models import CoinTransaction, Treasure, User, db

leaderboard_api = Blueprint("leaderboard_api", __name__)


def _count_by_user(query):
    """Run a (user_id, number) query and return it as a dict."""
    return dict(db.session.execute(query).all())


def player_rows():
    """Every player with their coins, treasures found and treasures hidden."""
    coins = _count_by_user(
        db.select(CoinTransaction.user_id, func.sum(CoinTransaction.amount))
        .group_by(CoinTransaction.user_id))
    found = _count_by_user(
        db.select(CoinTransaction.user_id, func.count())
        .where(CoinTransaction.reason == FOUND_REASON)
        .group_by(CoinTransaction.user_id))
    hidden = _count_by_user(
        db.select(Treasure.created_by, func.count())
        .where(Treasure.created_by.is_not(None))
        .group_by(Treasure.created_by))

    users = db.session.execute(db.select(User).order_by(User.id)).scalars().all()
    return [{"username": u.username, "coins": coins.get(u.id, 0),
             "found": found.get(u.id, 0), "hidden": hidden.get(u.id, 0)} for u in users]


@leaderboard_api.route("/leaderboard")
def leaderboard_page():
    return render_template("leaderboard.html")


@leaderboard_api.route("/api/leaderboard")
def leaderboard():
    """The top players, best first: rank, username, coins, found, hidden."""
    return jsonify(rank_players(player_rows()))

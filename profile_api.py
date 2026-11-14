"""Player profiles: /players/<username> (owner: B). Rules live in player_profile.py.

Like route_api.py, this lives in its own Blueprint. Avatars and names on the Community page,
in hunt chats and on the Leaderboard link here.
Only things other players can already see (the leaderboard, the feed) are shown.
"""

from flask import Blueprint, jsonify, render_template

from auth_api import current_user
from feed_rules import avatar, time_ago
from journey_log import format_duration
from leaderboard_api import player_rows
from models import HuntMember, Journey, Post, Treasure, User, db
from player_profile import (HIDDEN_SHOWN, RECENT_HUNTS, RECENT_POSTS, joined_label, parse_username, rank_of,
                            walk_totals)

profile_api = Blueprint("profile_api", __name__)


def _find(username):
    try:
        username = parse_username(username)
    except ValueError:
        return None
    return db.session.execute(db.select(User).where(User.username == username)).scalar_one_or_none()


@profile_api.route("/players/<username>")
def profile_page(username):
    # The page always loads; it asks the API and shows "No such player" if needed.
    return render_template("profile.html", username=username)


@profile_api.route("/api/players/<username>")
def profile(username):
    me = current_user()
    if me is None:
        return jsonify(error="Log in first"), 401
    player = _find(username)
    if player is None:
        return jsonify(error="No such player"), 404
    uid = player.id

    rows = player_rows()  # the same numbers as /leaderboard
    mine = next(r for r in rows if r["username"] == player.username)
    rank, players = rank_of(player.username, rows)

    journeys = db.session.execute(
        db.select(Journey).where(Journey.user_id == uid).order_by(Journey.id.desc())).scalars().all()
    hidden = db.session.execute(
        db.select(Treasure.name).where(Treasure.created_by == uid).order_by(Treasure.id.desc())
        .limit(HIDDEN_SHOWN)).scalars().all()
    posts = db.session.execute(
        db.select(Post).where(Post.user_id == uid, Post.journey_id.is_(None))
        .order_by(Post.id.desc()).limit(RECENT_POSTS)).scalars().all()
    in_hunts = db.session.execute(
        db.select(db.func.count()).select_from(HuntMember).where(HuntMember.user_id == uid)).scalar_one()

    return jsonify(
        username=player.username,
        avatar=avatar(player.username),
        joined=joined_label(player.created_at),
        is_me=uid == me.id,
        stats={
            "coins": mine["coins"],
            "found": mine["found"],
            "hidden": mine["hidden"],
            "rank": rank,
            "players": players,
            "in_hunts": in_hunts,
            **walk_totals([(j.distance_m, j.steps) for j in journeys]),
        },
        recent_hunts=[{"treasure": j.treasure.name, "distance_km": round(j.distance_m / 1000, 2),
                       "time": format_duration(j.duration_s), "ago": time_ago(j.created_at)}
                      for j in journeys[:RECENT_HUNTS]],
        hidden_treasures=hidden,
        recent_posts=[{"text": p.text, "ago": time_ago(p.created_at)} for p in posts],
    )

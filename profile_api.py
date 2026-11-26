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
from shop_api import has_badge  # A: the Explorer badge from the shop
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
    from leaderboard import on_the_board  # B: the same players as the Leaderboard page
    rank, players = rank_of(player.username, on_the_board(rows))

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
    races = _finished_races(uid, player.username, me.id)

    return jsonify(
        username=player.username,
        avatar=avatar(player.username),
        badge=has_badge(uid),  # A: bought the Explorer badge in the shop
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
        races=races,  # B: group hunt races this player was in, newest first
        hidden_treasures=hidden,
        # A share with no words of its own still shows up (B: shares, see shares.py).
        recent_posts=[{"id": p.id, "text": p.text or "Shared a post", "ago": time_ago(p.created_at)} for p in posts],
    )


def _finished_races(uid, username, viewer_id):
    """B: the finished hunt races this player was in, newest first (replay links for those who raced)."""
    from hunt_game_api import HuntGame  # here, not at the top: hunt_game_api imports much of the app
    from player_profile import race_result
    from models import Hunt
    rows = db.session.execute(
        db.select(Hunt, HuntGame, User.username)
        .join(HuntGame, HuntGame.hunt_id == Hunt.id)
        .join(HuntMember, HuntMember.hunt_id == Hunt.id)
        .outerjoin(User, User.id == HuntGame.winner_id)
        .where(HuntMember.user_id == uid, HuntGame.winner_id.is_not(None))
        .order_by(HuntGame.finished_at.desc(), Hunt.id.desc())
        .limit(RECENT_HUNTS)).all()
    races = []
    for hunt, game, winner in rows:
        viewer_raced = db.session.execute(db.select(HuntMember.id).where(
            HuntMember.hunt_id == hunt.id, HuntMember.user_id == viewer_id)).first() is not None
        races.append({"name": hunt.name, "result": race_result(winner, username, uid == viewer_id),
                      "ago": time_ago(game.finished_at or game.started_at),
                      "replay": f"/hunts/{hunt.id}/replay" if viewer_raced else None})
    return races

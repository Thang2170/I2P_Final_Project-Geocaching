"""The Community feed: posts, likes and comments, like a social news feed (owner: B).

Like route_api.py, this lives in its own Blueprint. Rules live in feed_rules.py.
Every finished hunt shows up as a post by itself; players can also write their own posts.
The page (/community) is served by journey_api.py.
"""

from flask import Blueprint, jsonify, request
from sqlalchemy.exc import IntegrityError

from auth_api import current_user
from feed_rules import (FEED_PAGE_SIZE, MAX_COMMENTS_SHOWN, avatar, like_summary, parse_comment,
                        parse_offset, parse_post, time_ago)
from journey_log import format_duration, format_pace
from models import Post, PostComment, PostLike, add_missing_hunt_posts, db

feed_api = Blueprint("feed_api", __name__)


def _login_needed():
    return jsonify(error="Log in first"), 401


def _add_missing_hunt_posts():
    try:
        add_missing_hunt_posts()
    except IntegrityError:  # another request added the same posts at the same moment
        db.session.rollback()


def _hunt_dict(journey):
    return {
        "treasure": journey.treasure.name,
        "distance_km": round(journey.distance_m / 1000, 2),
        "time": format_duration(journey.duration_s),
        "pace": format_pace(journey.distance_m, journey.duration_s),
        "steps": journey.steps,
        "calories": journey.calories,
    }


def _comment_dict(comment, me):
    return {
        "id": comment.id,
        "author": comment.user.username,
        "avatar": avatar(comment.user.username),
        "text": comment.text,
        "ago": time_ago(comment.created_at),
        "mine": comment.user_id == me.id,
    }


def _likes_of(post_id, me):
    likes = db.session.execute(db.select(PostLike).where(PostLike.post_id == post_id)
                               .order_by(PostLike.id.desc())).scalars().all()
    liked_by_me = any(like.user_id == me.id for like in likes)
    others = [like.user.username for like in likes if like.user_id != me.id]
    return {"likes": len(likes), "liked_by_me": liked_by_me, "like_summary": like_summary(others, liked_by_me)}


def _post_dict(post, me):
    comments = db.session.execute(db.select(PostComment).where(PostComment.post_id == post.id)
                                  .order_by(PostComment.id)).scalars().all()
    data = {
        "id": post.id,
        "author": post.user.username,
        "avatar": avatar(post.user.username),
        "mine": post.user_id == me.id,
        "ago": time_ago(post.created_at),
        "when": post.created_at.isoformat(),
        "text": post.text,
        "hunt": _hunt_dict(post.journey) if post.journey else None,
        # Hunt posts are part of the record, so only a player's own written posts can be deleted.
        "can_delete": post.user_id == me.id and post.journey_id is None,
        "comment_count": len(comments),
        "comments": [_comment_dict(c, me) for c in comments[-MAX_COMMENTS_SHOWN:]],
    }
    data.update(_likes_of(post.id, me))
    return data


def _find_post(post_id):
    return db.session.get(Post, post_id)


@feed_api.route("/api/feed")
def feed():
    """Newest posts first, FEED_PAGE_SIZE at a time. ?offset= gets the next page."""
    me = current_user()
    if me is None:
        return _login_needed()
    try:
        offset = parse_offset(request.args.get("offset"))
    except ValueError as err:
        return jsonify(error=str(err)), 400

    _add_missing_hunt_posts()
    query = (db.select(Post).order_by(Post.created_at.desc(), Post.id.desc())
             .offset(offset).limit(FEED_PAGE_SIZE + 1))  # one extra tells us if there is more
    posts = db.session.execute(query).scalars().all()
    more = len(posts) > FEED_PAGE_SIZE
    posts = posts[:FEED_PAGE_SIZE]
    return jsonify(
        me={"username": me.username, "avatar": avatar(me.username)},
        posts=[_post_dict(p, me) for p in posts],
        next_offset=offset + FEED_PAGE_SIZE if more else None)


@feed_api.route("/api/posts", methods=["POST"])
def create_post():
    """Write a post. Send JSON: text."""
    me = current_user()
    if me is None:
        return _login_needed()
    try:
        text = parse_post(request.get_json(silent=True))
    except ValueError as err:
        return jsonify(error=str(err)), 400
    post = Post(user_id=me.id, text=text)
    db.session.add(post)
    db.session.commit()
    return jsonify(_post_dict(post, me)), 201


@feed_api.route("/api/posts/<int:post_id>", methods=["DELETE"])
def delete_post(post_id):
    me = current_user()
    if me is None:
        return _login_needed()
    post = _find_post(post_id)
    if post is None:
        return jsonify(error="No such post"), 404
    if post.user_id != me.id:
        return jsonify(error="You can only delete your own posts"), 403
    if post.journey_id is not None:
        return jsonify(error="Hunt posts can't be deleted"), 403
    db.session.execute(db.delete(PostLike).where(PostLike.post_id == post.id))
    db.session.execute(db.delete(PostComment).where(PostComment.post_id == post.id))
    db.session.delete(post)
    db.session.commit()
    return jsonify(ok=True)


@feed_api.route("/api/posts/<int:post_id>/like", methods=["POST"])
def toggle_like(post_id):
    """Like a post, or take the like back if you already liked it."""
    me = current_user()
    if me is None:
        return _login_needed()
    if _find_post(post_id) is None:
        return jsonify(error="No such post"), 404
    existing = db.session.execute(db.select(PostLike).where(
        PostLike.post_id == post_id, PostLike.user_id == me.id)).scalar_one_or_none()
    if existing is None:
        db.session.add(PostLike(post_id=post_id, user_id=me.id))
    else:
        db.session.delete(existing)
    try:
        db.session.commit()
    except IntegrityError:  # a double tap: the first tap already saved the like
        db.session.rollback()
    return jsonify(_likes_of(post_id, me))


@feed_api.route("/api/posts/<int:post_id>/comments", methods=["POST"])
def add_comment(post_id):
    """Comment on a post. Send JSON: text."""
    me = current_user()
    if me is None:
        return _login_needed()
    if _find_post(post_id) is None:
        return jsonify(error="No such post"), 404
    try:
        text = parse_comment(request.get_json(silent=True))
    except ValueError as err:
        return jsonify(error=str(err)), 400
    comment = PostComment(post_id=post_id, user_id=me.id, text=text)
    db.session.add(comment)
    db.session.commit()
    return jsonify(_comment_dict(comment, me)), 201


@feed_api.route("/api/comments/<int:comment_id>", methods=["DELETE"])
def delete_comment(comment_id):
    me = current_user()
    if me is None:
        return _login_needed()
    comment = db.session.get(PostComment, comment_id)
    if comment is None:
        return jsonify(error="No such comment"), 404
    if comment.user_id != me.id:
        return jsonify(error="You can only delete your own comments"), 403
    db.session.delete(comment)
    db.session.commit()
    return jsonify(ok=True)

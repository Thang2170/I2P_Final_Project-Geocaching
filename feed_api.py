"""The Community feed: posts, likes and comments, like a social news feed (owner: B).

Like route_api.py, this lives in its own Blueprint. Rules live in feed_rules.py.
Every finished hunt shows up as a post by itself; players can also write their own posts.
The page (/community) is served by journey_api.py.
"""

from datetime import datetime, timezone

from flask import Blueprint, current_app, jsonify, request
from sqlalchemy.exc import IntegrityError

from auth_api import current_user
from feed_rules import (FEED_PAGE_SIZE, MAX_COMMENTS_SHOWN, avatar, like_summary, parse_comment, parse_offset,
                        parse_post, parse_reply, reply_start, time_ago)
from friends import parse_feed_filter
from friends_api import friend_ids_of
from journey_log import format_duration, format_pace
from models import (CommentReply, Notification, Post, PostComment, PostLike, PostShare, add_missing_hunt_posts,
                    db)
from notify_api import notify
from notify_rules import COMMENT, LIKE, REPLY, SHARE
from rate_limit import slow_down_message, wait_left
from shares import parse_share, share_target

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


def _reply_dict(reply, me):
    return {
        "id": reply.id,
        "author": reply.user.username,
        "avatar": avatar(reply.user.username),
        "text": reply.text,
        "ago": time_ago(reply.created_at),
        "mine": reply.user_id == me.id,
        "reply_start": reply_start(reply.user.username),  # tapping Reply on a reply starts "@name "
    }


def _comment_dict(comment, me):
    replies = db.session.execute(db.select(CommentReply).where(CommentReply.comment_id == comment.id)
                                 .order_by(CommentReply.id)).scalars().all()
    return {
        "id": comment.id,
        "author": comment.user.username,
        "avatar": avatar(comment.user.username),
        "text": comment.text,
        "ago": time_ago(comment.created_at),
        "mine": comment.user_id == me.id,
        "replies": [_reply_dict(r, me) for r in replies],  # B: shown indented under the comment
    }


def _likes_of(post_id, me):
    likes = db.session.execute(db.select(PostLike).where(PostLike.post_id == post_id)
                               .order_by(PostLike.id.desc())).scalars().all()
    liked_by_me = any(like.user_id == me.id for like in likes)
    others = [like.user.username for like in likes if like.user_id != me.id]
    return {"likes": len(likes), "liked_by_me": liked_by_me, "like_summary": like_summary(others, liked_by_me)}


def _share_link(post_id):
    """The PostShare row if this post shares another post, else None."""
    return db.session.execute(db.select(PostShare).where(PostShare.post_id == post_id)).scalar_one_or_none()


def _original_dict(post):
    """The shared post, boxed inside the share. None when it was deleted."""
    if post is None:
        return None
    return {
        "id": post.id,
        "author": post.user.username,
        "avatar": avatar(post.user.username),
        "ago": time_ago(post.created_at),
        "text": post.text,
        "hunt": _hunt_dict(post.journey) if post.journey else None,
    }


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
    # B: shares. A share boxes the original inside it ("shared" is None once that was deleted).
    link = _share_link(post.id)
    data["is_share"] = link is not None
    data["shared"] = _original_dict(_find_post(link.original_id)) if link and link.original_id else None
    data["share_count"] = db.session.execute(db.select(db.func.count()).select_from(PostShare).where(
        PostShare.original_id == post.id)).scalar_one()
    return data


def too_soon(kind, last_sent):
    """A 429 response if this player sent a `kind` too recently (see rate_limit.py), else None."""
    left = wait_left(last_sent, datetime.now(timezone.utc), current_app.config["SPAM_GAPS"][kind])
    if left:
        return jsonify(error=slow_down_message(left), wait_seconds=left), 429
    return None


def _last(model, user_id, *extra):
    """When this player last made a row of `model` (or None)."""
    query = db.select(model.created_at).where(model.user_id == user_id, *extra).order_by(model.id.desc()).limit(1)
    return db.session.execute(query).scalar_one_or_none()


def _find_post(post_id):
    return db.session.get(Post, post_id)


@feed_api.route("/api/feed")
def feed():
    """Newest posts first, FEED_PAGE_SIZE at a time. ?offset= gets the next page.

    ?only=friends shows only your friends' posts and your own (see friends.py).
    """
    me = current_user()
    if me is None:
        return _login_needed()
    try:
        offset = parse_offset(request.args.get("offset"))
        only = parse_feed_filter(request.args.get("only"))
    except ValueError as err:
        return jsonify(error=str(err)), 400

    _add_missing_hunt_posts()
    query = db.select(Post)
    if only == "friends":
        query = query.where(Post.user_id.in_([me.id, *friend_ids_of(me.id)]))
    query = (query.order_by(Post.created_at.desc(), Post.id.desc())
             .offset(offset).limit(FEED_PAGE_SIZE + 1))  # one extra tells us if there is more
    posts = db.session.execute(query).scalars().all()
    more = len(posts) > FEED_PAGE_SIZE
    posts = posts[:FEED_PAGE_SIZE]
    return jsonify(
        me={"username": me.username, "avatar": avatar(me.username)},
        only=only,
        posts=[_post_dict(p, me) for p in posts],
        next_offset=offset + FEED_PAGE_SIZE if more else None)


@feed_api.route("/api/posts/<int:post_id>")
def one_post(post_id):
    """One post with all its comments and replies, for its own page (/posts/<id>)."""
    me = current_user()
    if me is None:
        return _login_needed()
    post = _find_post(post_id)
    if post is None:
        return jsonify(error="This post was deleted, or it never existed."), 404
    return jsonify(me={"username": me.username, "avatar": avatar(me.username)}, post=_post_dict(post, me))


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
    wait = too_soon("post", _last(Post, me.id, Post.journey_id.is_(None)))  # hunt posts don't count
    if wait:
        return wait
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
    comment_ids = db.select(PostComment.id).where(PostComment.post_id == post.id)
    db.session.execute(db.delete(CommentReply).where(CommentReply.comment_id.in_(comment_ids)))
    db.session.execute(db.delete(PostComment).where(PostComment.post_id == post.id))
    db.session.execute(db.delete(Notification).where(Notification.post_id == post.id))
    # B: shares. If this was a share, its link goes; shares OF this post now say "This post was deleted".
    db.session.execute(db.delete(PostShare).where(PostShare.post_id == post.id))
    db.session.execute(db.update(PostShare).where(PostShare.original_id == post.id).values(original_id=None))
    db.session.delete(post)
    db.session.commit()
    return jsonify(ok=True)


@feed_api.route("/api/posts/<int:post_id>/share", methods=["POST"])
def share_post(post_id):
    """Share a post to the feed, with your own words if you like. Send JSON: text (optional)."""
    me = current_user()
    if me is None:
        return _login_needed()
    post = _find_post(post_id)
    if post is None:
        return jsonify(error="No such post"), 404
    try:
        text = parse_share(request.get_json(silent=True))
        link = _share_link(post.id)
        target_id = share_target(post.id, link is not None, link.original_id if link else None)
    except ValueError as err:
        return jsonify(error=str(err)), 400
    wait = too_soon("post", _last(Post, me.id, Post.journey_id.is_(None)))  # a share counts as a post
    if wait:
        return wait
    original = _find_post(target_id)
    share = Post(user_id=me.id, text=text)
    db.session.add(share)
    db.session.flush()  # gives the share its id
    db.session.add(PostShare(post_id=share.id, original_id=original.id))
    notify(original.user_id, SHARE, actor_id=me.id, post_id=original.id)
    db.session.commit()
    return jsonify(_post_dict(share, me)), 201


@feed_api.route("/api/posts/<int:post_id>/likes")
def who_liked(post_id):
    """Everyone who liked a post, newest first (tap "♥ ann and 2 others" to see them)."""
    me = current_user()
    if me is None:
        return _login_needed()
    if _find_post(post_id) is None:
        return jsonify(error="No such post"), 404
    likes = db.session.execute(db.select(PostLike).where(PostLike.post_id == post_id)
                               .order_by(PostLike.id.desc())).scalars().all()
    return jsonify(likes=[{"username": like.user.username, "avatar": avatar(like.user.username),
                           "is_me": like.user_id == me.id} for like in likes])


@feed_api.route("/api/posts/<int:post_id>/like", methods=["POST"])
def toggle_like(post_id):
    """Like a post, or take the like back if you already liked it."""
    me = current_user()
    if me is None:
        return _login_needed()
    post = _find_post(post_id)
    if post is None:
        return jsonify(error="No such post"), 404
    existing = db.session.execute(db.select(PostLike).where(
        PostLike.post_id == post_id, PostLike.user_id == me.id)).scalar_one_or_none()
    if existing is None:
        db.session.add(PostLike(post_id=post_id, user_id=me.id))
        notify(post.user_id, LIKE, actor_id=me.id, post_id=post_id)  # the bell for the post's author
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
    post = _find_post(post_id)
    if post is None:
        return jsonify(error="No such post"), 404
    try:
        text = parse_comment(request.get_json(silent=True))
    except ValueError as err:
        return jsonify(error=str(err)), 400
    wait = too_soon("comment", _last(PostComment, me.id))
    if wait:
        return wait
    comment = PostComment(post_id=post_id, user_id=me.id, text=text)
    db.session.add(comment)
    notify(post.user_id, COMMENT, actor_id=me.id, post_id=post_id)
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
    db.session.execute(db.delete(CommentReply).where(CommentReply.comment_id == comment.id))  # its replies go too
    db.session.delete(comment)
    db.session.commit()
    return jsonify(ok=True)


@feed_api.route("/api/comments/<int:comment_id>/replies", methods=["POST"])
def add_reply(comment_id):
    """Reply to a comment. Send JSON: text. The commenter gets a notification."""
    me = current_user()
    if me is None:
        return _login_needed()
    comment = db.session.get(PostComment, comment_id)
    if comment is None:
        return jsonify(error="No such comment"), 404
    try:
        text = parse_reply(request.get_json(silent=True))
    except ValueError as err:
        return jsonify(error=str(err)), 400
    wait = too_soon("reply", _last(CommentReply, me.id))
    if wait:
        return wait
    reply = CommentReply(comment_id=comment.id, user_id=me.id, text=text)
    db.session.add(reply)
    notify(comment.user_id, REPLY, actor_id=me.id, post_id=comment.post_id)
    db.session.commit()
    return jsonify(_reply_dict(reply, me)), 201


@feed_api.route("/api/replies/<int:reply_id>", methods=["DELETE"])
def delete_reply(reply_id):
    me = current_user()
    if me is None:
        return _login_needed()
    reply = db.session.get(CommentReply, reply_id)
    if reply is None:
        return jsonify(error="No such reply"), 404
    if reply.user_id != me.id:
        return jsonify(error="You can only delete your own replies"), 403
    db.session.delete(reply)
    db.session.commit()
    return jsonify(ok=True)

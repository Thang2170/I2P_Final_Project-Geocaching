"""Notifications: the bell in the top bar (owner: B). Rules live in notify_rules.py.

Like route_api.py, this lives in its own Blueprint.
feed_api.py and hunt_api.py call notify() when something happens; the bell asks
GET /api/notifications and, when opened, POST /api/notifications/seen.
"""

from flask import Blueprint, jsonify

from auth_api import current_user
from feed_rules import avatar, time_ago
from models import Hunt, Notification, Post, db
from notify_rules import SHOWN, link, message, short, should_notify

notify_api = Blueprint("notify_api", __name__)


def notify(recipient_id, kind, actor_id=None, post_id=None, hunt_id=None):
    """Save a notification (the caller commits). Skips your own actions and unread doubles."""
    if actor_id is not None and not should_notify(actor_id, recipient_id):
        return
    # Like, unlike, like again: one unread notification is enough.
    double = db.session.execute(db.select(Notification.id).where(
        Notification.user_id == recipient_id, Notification.kind == kind, Notification.actor_id == actor_id,
        Notification.post_id == post_id, Notification.hunt_id == hunt_id,
        Notification.seen.is_(False)).limit(1)).first()
    if double is None:
        db.session.add(Notification(user_id=recipient_id, kind=kind, actor_id=actor_id,
                                    post_id=post_id, hunt_id=hunt_id))


def _item(n):
    subject = ""
    if n.post_id is not None:
        post = db.session.get(Post, n.post_id)
        if post is None:
            subject = "a deleted post"
        elif post.journey is not None:  # an automatic hunt post has no text of its own
            subject = short(f"Found {post.journey.treasure.name}")
        else:
            subject = short(post.text)
    elif n.hunt_id is not None:
        hunt = db.session.get(Hunt, n.hunt_id)
        subject = hunt.name if hunt else "a hunt"
    actor = n.actor.username if n.actor else None
    return {
        "id": n.id,
        "text": message(n.kind, actor, subject),
        "link": link(n.kind, post_id=n.post_id, hunt_id=n.hunt_id),
        "avatar": avatar(actor) if actor else None,
        "ago": time_ago(n.created_at),
        "seen": n.seen,
    }


@notify_api.route("/api/notifications")
def notifications():
    """Your newest notifications and how many you haven't seen."""
    user = current_user()
    if user is None:
        return jsonify(error="Log in first"), 401
    items = db.session.execute(db.select(Notification).where(Notification.user_id == user.id)
                               .order_by(Notification.id.desc()).limit(SHOWN)).scalars().all()
    unseen = db.session.execute(db.select(db.func.count()).select_from(Notification).where(
        Notification.user_id == user.id, Notification.seen.is_(False))).scalar_one()
    return jsonify(unseen=unseen, items=[_item(n) for n in items])


@notify_api.route("/api/notifications/seen", methods=["POST"])
def mark_seen():
    """You opened the bell: everything in it counts as seen."""
    user = current_user()
    if user is None:
        return jsonify(error="Log in first"), 401
    db.session.execute(db.update(Notification).where(
        Notification.user_id == user.id, Notification.seen.is_(False)).values(seen=True))
    db.session.commit()
    return jsonify(unseen=0)

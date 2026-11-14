"""Group chat for each hunt (owner: B). Rules live in hunt_chat.py.

Like route_api.py, this lives in its own Blueprint.
The page /hunts/<id>/chat loads the latest messages, then asks every few seconds
for anything newer (GET /api/hunts/<id>/messages?after=<last id>).
"""

from flask import Blueprint, abort, jsonify, render_template, request

from auth_api import current_user
from feed_rules import avatar, time_ago
from hunt_chat import HISTORY_SIZE, POLL_SECONDS, chat_access, parse_after, parse_message
from models import Hunt, HuntMember, HuntMessage, User, db
from queue_logic import queue_status

chat_api = Blueprint("chat_api", __name__)


def _member_ids(hunt_id):
    """Everyone in the hunt, in the order they joined (the same order hunt_api.py uses)."""
    query = db.select(HuntMember.user_id).where(HuntMember.hunt_id == hunt_id).order_by(HuntMember.id)
    return db.session.execute(query).scalars().all()


def _message_dict(message, me):
    return {
        "id": message.id,
        "author": message.user.username,
        "avatar": avatar(message.user.username),
        "text": message.text,
        "ago": time_ago(message.created_at),
        "mine": message.user_id == me.id,
    }


def _members(hunt, member_ids):
    """Who is in the hunt, playing ones first, for the strip at the top of the chat."""
    names = dict(db.session.execute(db.select(User.id, User.username).where(User.id.in_(member_ids))).all())
    return [{"username": names[uid], "avatar": avatar(names[uid]),
             "state": queue_status(uid, member_ids, hunt.capacity)["state"]}
            for uid in member_ids if uid in names]


def _open_chat(hunt_id):
    """(user, hunt, member_ids) or an error response to send back."""
    user = current_user()
    if user is None:
        return None, (jsonify(error="Log in first"), 401)
    hunt = db.session.get(Hunt, hunt_id)
    if hunt is None:
        return None, (jsonify(error="No such hunt"), 404)
    member_ids = _member_ids(hunt_id)
    allowed, reason = chat_access(user.id, member_ids, hunt.capacity)
    if not allowed:  # not in the hunt, or still waiting in line
        return None, (jsonify(error=reason), 403)
    return (user, hunt, member_ids), None


@chat_api.route("/hunts/<int:hunt_id>/chat")
def chat_page(hunt_id):
    if db.session.get(Hunt, hunt_id) is None:
        abort(404)
    return render_template("chat.html", hunt_id=hunt_id, poll_seconds=POLL_SECONDS)


@chat_api.route("/api/hunts/<int:hunt_id>/messages")
def list_messages(hunt_id):
    """The latest messages (oldest first), or only the ones after ?after=<id>."""
    opened, error = _open_chat(hunt_id)
    if error:
        return error
    user, hunt, member_ids = opened
    try:
        after = parse_after(request.args.get("after"))
    except ValueError as err:
        return jsonify(error=str(err)), 400

    query = db.select(HuntMessage).where(HuntMessage.hunt_id == hunt_id)
    if after:
        query = query.where(HuntMessage.id > after).order_by(HuntMessage.id)
        messages = db.session.execute(query.limit(HISTORY_SIZE)).scalars().all()
    else:  # the newest HISTORY_SIZE, shown oldest first like any chat
        newest = db.session.execute(query.order_by(HuntMessage.id.desc()).limit(HISTORY_SIZE)).scalars().all()
        messages = list(reversed(newest))

    return jsonify(
        hunt={"id": hunt.id, "name": hunt.name, "capacity": hunt.capacity},
        me={"username": user.username, "avatar": avatar(user.username),
            "status": queue_status(user.id, member_ids, hunt.capacity)},
        members=_members(hunt, member_ids),
        messages=[_message_dict(m, user) for m in messages])


@chat_api.route("/api/hunts/<int:hunt_id>/messages", methods=["POST"])
def send_message(hunt_id):
    """Send a message to the hunt's chat. Send JSON: text."""
    opened, error = _open_chat(hunt_id)
    if error:
        return error
    user, hunt, _ = opened
    try:
        text = parse_message(request.get_json(silent=True))
    except ValueError as err:
        return jsonify(error=str(err)), 400
    message = HuntMessage(hunt_id=hunt.id, user_id=user.id, text=text)
    db.session.add(message)
    db.session.commit()
    return jsonify(_message_dict(message, user)), 201

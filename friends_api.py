"""Friends: ask, accept, decline, unfriend, and the friends list (owner: B). Rules: friends.py.

Like route_api.py, this lives in its own Blueprint.
- GET  /api/players/<name>/friends      their friends, and how you are linked to them
- POST /api/friends/<name>/request      "Add friend" (if they already asked you, you become friends)
- POST /api/friends/<name>/accept       say yes to their request
- POST /api/friends/<name>/decline      say no to their request
- POST /api/friends/<name>/remove       unfriend, or take back a request you sent
The profile page and the bell call these. The feed's Friends switch uses friend_ids_of().
"""

from datetime import datetime, timezone

from flask import Blueprint, jsonify
from sqlalchemy.exc import IntegrityError

from auth_api import current_user
from feed_rules import avatar
from friends import (ACCEPTED, FRIENDS_SHOWN, PENDING, check_answer, check_remove, friend_ids, relation,
                     request_action)
from models import Friendship, Notification, User, db
from notify_api import notify
from notify_rules import FRIEND_ACCEPTED, FRIEND_REQUEST
from player_profile import parse_username

friends_api = Blueprint("friends_api", __name__)


def _player(username):
    try:
        username = parse_username(username)
    except ValueError:
        return None
    return db.session.execute(db.select(User).where(User.username == username)).scalar_one_or_none()


def pair_row(a_id, b_id):
    """The Friendship row between two players, whichever of them asked, or None."""
    return db.session.execute(db.select(Friendship).where(db.or_(
        db.and_(Friendship.requester_id == a_id, Friendship.addressee_id == b_id),
        db.and_(Friendship.requester_id == b_id, Friendship.addressee_id == a_id)))).scalar_one_or_none()


def _as_tuple(row):
    return (row.requester_id, row.addressee_id, row.status) if row else None


def link_between(me_id, other_id):
    """friends.relation() for two players, read from the database."""
    return relation(me_id, other_id, _as_tuple(pair_row(me_id, other_id)))


def friend_ids_of(user_id):
    rows = db.session.execute(db.select(Friendship.requester_id, Friendship.addressee_id, Friendship.status)
                              .where(db.or_(Friendship.requester_id == user_id,
                                            Friendship.addressee_id == user_id))).all()
    return friend_ids(user_id, [tuple(r) for r in rows])


def _drop_request_notification(recipient_id, actor_id):
    """The request was answered or taken back: its Accept/Decline buttons go away."""
    db.session.execute(db.delete(Notification).where(
        Notification.user_id == recipient_id, Notification.actor_id == actor_id,
        Notification.kind == FRIEND_REQUEST))


def _answer(me, other, state, status=200):
    return jsonify(username=other.username, state=state), status


@friends_api.route("/api/players/<username>/friends")
def friends_of(username):
    me = current_user()
    if me is None:
        return jsonify(error="Log in first"), 401
    player = _player(username)
    if player is None:
        return jsonify(error="No such player"), 404
    ids = friend_ids_of(player.id)
    names = []
    if ids:
        names = db.session.execute(db.select(User.username).where(User.id.in_(ids))
                                   .order_by(User.username)).scalars().all()
    incoming = 0
    if player.id == me.id:  # your own profile also shows how many are waiting for an answer
        incoming = db.session.execute(db.select(db.func.count()).select_from(Friendship).where(
            Friendship.addressee_id == me.id, Friendship.status == PENDING)).scalar_one()
    return jsonify(
        username=player.username,
        state=link_between(me.id, player.id),
        count=len(names),
        friends=[{"username": n, "avatar": avatar(n)} for n in names[:FRIENDS_SHOWN]],
        requests_waiting=incoming,
    )


def _me_and_other(username):
    me = current_user()
    if me is None:
        return None, None, (jsonify(error="Log in first"), 401)
    other = _player(username)
    if other is None:
        return me, None, (jsonify(error="No such player"), 404)
    return me, other, None


@friends_api.route("/api/friends/<username>/request", methods=["POST"])
def send_request(username):
    me, other, error = _me_and_other(username)
    if error:
        return error
    row = pair_row(me.id, other.id)
    try:
        action = request_action(me.id, other.id, _as_tuple(row))
    except ValueError as err:
        return jsonify(error=str(err)), 400
    if action == "accept":  # they had already asked you: saying "add" too means yes
        return _accept(me, other, row)
    db.session.add(Friendship(requester_id=me.id, addressee_id=other.id, status=PENDING))
    notify(other.id, FRIEND_REQUEST, actor_id=me.id)
    try:
        db.session.commit()
    except IntegrityError:  # two taps at the same moment
        db.session.rollback()
        return jsonify(error="You already asked. Wait for an answer."), 400
    return _answer(me, other, link_between(me.id, other.id), 201)


def _accept(me, other, row):
    row.status = ACCEPTED
    row.answered_at = datetime.now(timezone.utc)
    _drop_request_notification(me.id, other.id)
    notify(other.id, FRIEND_ACCEPTED, actor_id=me.id)
    db.session.commit()
    return _answer(me, other, link_between(me.id, other.id))


@friends_api.route("/api/friends/<username>/accept", methods=["POST"])
def accept(username):
    me, other, error = _me_and_other(username)
    if error:
        return error
    row = pair_row(me.id, other.id)
    try:
        check_answer(me.id, other.id, _as_tuple(row))
    except ValueError as err:
        return jsonify(error=str(err)), 400
    return _accept(me, other, row)


@friends_api.route("/api/friends/<username>/decline", methods=["POST"])
def decline(username):
    me, other, error = _me_and_other(username)
    if error:
        return error
    row = pair_row(me.id, other.id)
    try:
        check_answer(me.id, other.id, _as_tuple(row))
    except ValueError as err:
        return jsonify(error=str(err)), 400
    db.session.delete(row)  # they are not told; they can ask again later
    _drop_request_notification(me.id, other.id)
    db.session.commit()
    return _answer(me, other, link_between(me.id, other.id))


@friends_api.route("/api/friends/<username>/remove", methods=["POST"])
def remove(username):
    me, other, error = _me_and_other(username)
    if error:
        return error
    row = pair_row(me.id, other.id)
    try:
        check_remove(me.id, other.id, _as_tuple(row))
    except ValueError as err:
        return jsonify(error=str(err)), 400
    if row.status == PENDING:  # taking back a request: it leaves their bell too
        _drop_request_notification(other.id, me.id)
    db.session.delete(row)
    db.session.commit()
    return _answer(me, other, link_between(me.id, other.id))

"""Register, log in and log out (Feature: simple login, owner: B).

Like route_api.py, this lives in its own Blueprint. app.py registers it and sets
the SECRET_KEY that Flask uses to sign the login cookie.
"""

from flask import Blueprint, jsonify, render_template, request, session
from sqlalchemy.exc import IntegrityError

from datetime import datetime, timedelta, timezone

from login_guard import WINDOW_S, lock_text, locked_for, recent_fails, tries_left_text
from models import LoginFailure, User, db
from user_input import parse_login, parse_new_account

auth_api = Blueprint("auth_api", __name__)

WRONG_LOGIN = "Wrong username or password"


def current_user():
    """Return the logged-in User, or None."""
    user_id = session.get("user_id")
    if user_id is None:
        return None
    return db.session.get(User, user_id)


def _find_user(username):
    return db.session.execute(db.select(User).filter_by(username=username)).scalar_one_or_none()


def _request_data():
    data = request.get_json(silent=True)
    return request.form.to_dict() if data is None else data


@auth_api.route("/login")
def login_page():
    return render_template("login.html")


@auth_api.route("/api/register", methods=["POST"])
def register():
    try:
        username, password = parse_new_account(_request_data())
    except ValueError as err:
        return jsonify(error=str(err)), 400

    if _find_user(username) is not None:
        return jsonify(error="That username is taken"), 409

    user = User(username=username)
    user.set_password(password)
    db.session.add(user)
    try:
        db.session.commit()
    except IntegrityError:  # someone registered the same name a moment ago
        db.session.rollback()
        return jsonify(error="That username is taken"), 409

    session.clear()
    session["user_id"] = user.id  # a new account is logged in straight away
    return jsonify(user.to_dict()), 201


@auth_api.route("/api/login", methods=["POST"])
def login():
    try:
        username, password = parse_login(_request_data())
    except ValueError as err:
        return jsonify(error=str(err)), 400

    # B: slow down password guessing (login_guard.py)
    key, place, now = username.lower(), _place(), _now()
    db.session.execute(db.delete(LoginFailure).where(
        LoginFailure.username == key, LoginFailure.at < now - timedelta(seconds=WINDOW_S)))
    fails = db.session.execute(db.select(LoginFailure.at).where(
        LoginFailure.username == key, LoginFailure.place == place)).scalars().all()
    wait = locked_for(fails, now)
    if wait:
        db.session.commit()
        response = jsonify(error=lock_text(wait), retry_after_s=wait)
        response.headers["Retry-After"] = str(wait)
        return response, 429

    user = _find_user(username)
    if user is None or not user.check_password(password):
        db.session.add(LoginFailure(username=key, place=place, at=now))
        db.session.commit()
        wait = locked_for([*fails, now], now)
        if wait:  # this was the last allowed try: say so now, not on the next one
            response = jsonify(error=lock_text(wait), retry_after_s=wait)
            response.headers["Retry-After"] = str(wait)
            return response, 429
        return jsonify(error=WRONG_LOGIN + "." + tries_left_text(len(recent_fails(fails, now)) + 1)), 401

    db.session.execute(db.delete(LoginFailure).where(LoginFailure.username == key, LoginFailure.place == place))
    db.session.commit()
    session.clear()
    session["user_id"] = user.id
    return jsonify(user.to_dict())


def _now():
    """B: naive UTC, like everything the database keeps."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _place():
    """B: where a login try comes from (the address; a hosting proxy may make this the same for all)."""
    return (request.remote_addr or "unknown")[:64]


@auth_api.route("/api/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify(ok=True)


@auth_api.route("/api/me")
def me():
    user = current_user()
    if user is None:
        return jsonify(error="Not logged in"), 401
    return jsonify(user.to_dict())

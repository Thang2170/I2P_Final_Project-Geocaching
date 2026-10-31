"""Register, log in and log out (Feature: simple login, owner: B).

Like route_api.py, this lives in its own Blueprint. app.py registers it and sets
the SECRET_KEY that Flask uses to sign the login cookie.
"""

from flask import Blueprint, jsonify, render_template, request, session
from sqlalchemy.exc import IntegrityError

from models import User, db
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

    user = _find_user(username)
    if user is None or not user.check_password(password):
        return jsonify(error=WRONG_LOGIN), 401

    session.clear()
    session["user_id"] = user.id
    return jsonify(user.to_dict())


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

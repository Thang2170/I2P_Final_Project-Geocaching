"""Earn and check coins (Feature 9, owner: B). Rules live in coins.py.

Like route_api.py, this lives in its own Blueprint.
The phone only sends where the player is: Python measures the distance and decides.
"""

from flask import Blueprint, jsonify, request
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from auth_api import current_user
from coins import ALREADY_FOUND, COINS_PER_FIND, OWN_TREASURE, TOO_FAR, claim_problem
from location import FOUND_RADIUS_M, haversine_m
from models import CoinTransaction, Treasure, db
from treasure_input import parse_number

coin_api = Blueprint("coin_api", __name__)

FOUND_REASON = "found_treasure"

# claim problem -> (HTTP status, message)
PROBLEMS = {
    OWN_TREASURE: (403, "You hid this treasure yourself, so it earns you no coins."),
    ALREADY_FOUND: (409, "You already found this treasure."),
}


def get_balance(user_id):
    """Total coins a player has: the sum of their ledger."""
    query = db.select(func.coalesce(func.sum(CoinTransaction.amount), 0)).where(
        CoinTransaction.user_id == user_id)
    return db.session.execute(query).scalar_one()


def found_treasure_ids(user_id):
    """The ids of the treasures this player has been paid for."""
    query = db.select(CoinTransaction.treasure_id).where(
        CoinTransaction.user_id == user_id, CoinTransaction.reason == FOUND_REASON,
        CoinTransaction.treasure_id.is_not(None))  # a find always names its treasure
    return sorted(db.session.execute(query).scalars().all())


@coin_api.route("/api/coins")
def coins():
    """The logged-in player's coin balance and the treasures they have found."""
    user = current_user()
    if user is None:
        return jsonify(error="Log in first"), 401
    return jsonify(balance=get_balance(user.id), found_treasure_ids=found_treasure_ids(user.id),
                   coins_per_find=COINS_PER_FIND)


@coin_api.route("/api/treasures/<int:treasure_id>/claim", methods=["POST"])
def claim_treasure(treasure_id):
    """Claim the coins for a treasure. Send JSON or form fields: lat, lon (where you are)."""
    user = current_user()
    if user is None:
        return jsonify(error="Log in first"), 401

    treasure = db.session.get(Treasure, treasure_id)
    if treasure is None:
        return jsonify(error="No such treasure"), 404

    data = request.get_json(silent=True)
    if data is None:
        data = request.form.to_dict()
    if not isinstance(data, dict):
        return jsonify(error="Send your lat and lon"), 400
    try:
        lat = parse_number(data.get("lat"), "lat", -90, 90)
        lon = parse_number(data.get("lon"), "lon", -180, 180)
    except ValueError as err:
        return jsonify(error=str(err)), 400

    distance_m = haversine_m(lat, lon, treasure.lat, treasure.lon)
    already_found = treasure_id in found_treasure_ids(user.id)
    problem = claim_problem(distance_m, user.id, treasure.created_by, already_found)

    if problem == TOO_FAR:
        return jsonify(error=f"You are {round(distance_m)} m away. "
                             f"Get within {FOUND_RADIUS_M} m to find it.",
                       distance_m=round(distance_m, 1)), 400
    if problem is not None:
        status, message = PROBLEMS[problem]
        return jsonify(error=message), status

    db.session.add(CoinTransaction(user_id=user.id, amount=COINS_PER_FIND,
                                   reason=FOUND_REASON, treasure_id=treasure_id))
    try:
        db.session.commit()
    except IntegrityError:  # a double tap: the other request was paid a moment ago
        db.session.rollback()
        return jsonify(error=PROBLEMS[ALREADY_FOUND][1]), 409

    return jsonify(treasure=treasure.name, coins_earned=COINS_PER_FIND, balance=get_balance(user.id))

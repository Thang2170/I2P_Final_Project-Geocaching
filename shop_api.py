"""The shop: spend coins on items and vouchers (Feature 9, owner: B). Rules live in shop.py.

Like route_api.py, this lives in its own Blueprint.
"""

from flask import Blueprint, jsonify, render_template, request
from sqlalchemy.exc import IntegrityError

from auth_api import current_user
from coin_api import get_balance
from models import CoinTransaction, Purchase, db
from shop import (ALREADY_OWNED, ITEMS, NOT_ENOUGH_COINS, UNKNOWN_ITEM, find_item,
                  item_to_dict, make_voucher_code, purchase_problem)

shop_api = Blueprint("shop_api", __name__)

SHOP_REASON = "shop"

# purchase problem -> (HTTP status, message)
PROBLEMS = {
    UNKNOWN_ITEM: (404, "No such item."),
    ALREADY_OWNED: (409, "You already have this one."),
    NOT_ENOUGH_COINS: (402, "Not enough coins yet. Go and find more treasures!"),
}


def _owned_item_ids(user_id):
    query = db.select(Purchase.item_id).where(Purchase.user_id == user_id)
    return set(db.session.execute(query).scalars().all())


@shop_api.route("/shop")
def shop_page():
    return render_template("shop.html")


@shop_api.route("/api/shop/items")
def list_items():
    """Everything for sale. When logged in, each item also says whether you own it."""
    user = current_user()
    owned = _owned_item_ids(user.id) if user else set()
    return jsonify([{**item_to_dict(item), "owned": item.once and item.id in owned} for item in ITEMS])


@shop_api.route("/api/shop/buy", methods=["POST"])
def buy():
    """Buy an item. Send JSON or a form field: item_id."""
    user = current_user()
    if user is None:
        return jsonify(error="Log in first"), 401

    data = request.get_json(silent=True)
    if data is None:
        data = request.form.to_dict()
    item_id = data.get("item_id") if isinstance(data, dict) else None
    if not isinstance(item_id, str) or not item_id:
        return jsonify(error="item_id is required"), 400

    item = find_item(item_id)
    balance = get_balance(user.id)
    problem = purchase_problem(item, balance, item_id in _owned_item_ids(user.id))
    if problem is not None:
        status, message = PROBLEMS[problem]
        return jsonify(error=message), status

    code = make_voucher_code() if item.kind == "voucher" else None
    # Both rows are saved in one commit: either you pay and get the item, or neither happens.
    db.session.add(Purchase(user_id=user.id, item_id=item.id, price=item.price, voucher_code=code))
    db.session.add(CoinTransaction(user_id=user.id, amount=-item.price, reason=SHOP_REASON))
    try:
        db.session.commit()
    except IntegrityError:  # a clash on the random code (very unlikely): nothing was charged
        db.session.rollback()
        return jsonify(error="Something went wrong. Please try again."), 409

    return jsonify(item=item_to_dict(item), voucher_code=code, balance=get_balance(user.id))


@shop_api.route("/api/shop/purchases")
def purchases():
    """What the logged-in player has bought, newest first."""
    user = current_user()
    if user is None:
        return jsonify(error="Log in first"), 401
    rows = db.session.execute(
        db.select(Purchase).where(Purchase.user_id == user.id).order_by(Purchase.id.desc())
    ).scalars().all()
    result = []
    for row in rows:
        item = find_item(row.item_id)
        result.append({"item_id": row.item_id, "name": item.name if item else row.item_id,
                       "price": row.price, "voucher_code": row.voucher_code,
                       "bought_at": row.created_at.isoformat()})
    return jsonify(result)

"""The box that proves you were there (owner: B). Rules: box_code.py. The ESP32 side: esp32/box_main.py.

- GET    /box                                   the page
- GET    /api/boxes                             treasures with a box, and whether you proved each one
- POST   /api/treasures/<id>/box                add a box (who hid it, or an admin); shows the secret ONCE
- DELETE /api/treasures/<id>/box                take the box away
- POST   /api/treasures/<id>/box/proof          {"code": "123456"} typed from the box's screen

While a treasure has a box, coin_api.py refuses to pay for it until you proved you were there.
"""

import time

from flask import Blueprint, jsonify, redirect, render_template, request
from sqlalchemy.exc import IntegrityError

from admin_api import is_admin
from auth_api import current_user
from box_code import CODE_USED, STEP_S, check_code, new_secret
from models import BoxProof, Treasure, TreasureBox, db
from play_input import may_manage

box_api = Blueprint("box_api", __name__)

NEEDS_PROOF = "This treasure has a box. Type the code on its screen first (Box page)."


def _now():
    return time.time()  # (tests patch this)


def _box(treasure_id):
    return db.session.execute(db.select(TreasureBox).filter_by(treasure_id=treasure_id)).scalar_one_or_none()


def _proved(box_id, user_id):
    return db.session.execute(db.select(BoxProof.id).filter_by(box_id=box_id, user_id=user_id)).first() is not None


def claim_refusal(treasure, user_id):
    """For coin_api.py: a message if this treasure has a box and the player has not typed its code."""
    box = _box(treasure.id)
    if box is None or _proved(box.id, user_id):
        return None
    return NEEDS_PROOF


@box_api.route("/box")
def box_page():
    if current_user() is None:
        return redirect("/login?next=/box")
    return render_template("box.html")


@box_api.route("/api/boxes")
def list_boxes():
    me = current_user()
    if me is None:
        return jsonify(error="Log in first"), 401
    rows = db.session.execute(db.select(TreasureBox, Treasure).join(Treasure, Treasure.id == TreasureBox.treasure_id)
                              .order_by(Treasure.name)).all()
    proved = set(db.session.execute(db.select(BoxProof.box_id).filter_by(user_id=me.id)).scalars())
    admin = is_admin(me)
    boxes = [{"treasure_id": t.id, "treasure": t.name, "proved": box.id in proved,
              "mine": may_manage(me.id, t.created_by, admin)} for box, t in rows]
    boxed = {b["treasure_id"] for b in boxes}
    mine = db.session.execute(db.select(Treasure).order_by(Treasure.name)).scalars()
    can_add = [{"id": t.id, "name": t.name} for t in mine
               if t.id not in boxed and may_manage(me.id, t.created_by, admin)]
    return jsonify(boxes=boxes, can_add=can_add, step_s=STEP_S)


def _managed_treasure(treasure_id):
    """(treasure, None) or (None, error response) for adding or removing a box."""
    me = current_user()
    if me is None:
        return None, (jsonify(error="Log in first"), 401)
    treasure = db.session.get(Treasure, treasure_id)
    if treasure is None:
        return None, (jsonify(error="No such treasure"), 404)
    if not may_manage(me.id, treasure.created_by, is_admin(me)):
        return None, (jsonify(error="Only the player who hid this treasure can give it a box"), 403)
    return treasure, None


@box_api.route("/api/treasures/<int:treasure_id>/box", methods=["POST"])
def add_box(treasure_id):
    treasure, error = _managed_treasure(treasure_id)
    if error:
        return error
    if _box(treasure.id) is not None:
        return jsonify(error="This treasure already has a box"), 409
    box = TreasureBox(treasure_id=treasure.id, secret=new_secret(), created_by=current_user().id)
    db.session.add(box)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify(error="This treasure already has a box"), 409
    # The only time the secret leaves the server: it goes in the ESP32's config.py.
    return jsonify(treasure=treasure.name, treasure_id=treasure.id, secret=box.secret,
                   note="Copy this into BOX_SECRET in the ESP32's config.py now. It is not shown again."), 201


@box_api.route("/api/treasures/<int:treasure_id>/box", methods=["DELETE"])
def remove_box(treasure_id):
    treasure, error = _managed_treasure(treasure_id)
    if error:
        return error
    box = _box(treasure.id)
    if box is None:
        return jsonify(error="This treasure has no box"), 404
    db.session.execute(db.delete(BoxProof).where(BoxProof.box_id == box.id))
    db.session.delete(box)
    db.session.commit()
    return jsonify(ok=True)


@box_api.route("/api/treasures/<int:treasure_id>/box/proof", methods=["POST"])
def prove(treasure_id):
    me = current_user()
    if me is None:
        return jsonify(error="Log in first"), 401
    treasure = db.session.get(Treasure, treasure_id)
    box = _box(treasure_id) if treasure else None
    if box is None:
        return jsonify(error="This treasure has no box"), 404
    if _proved(box.id, me.id):
        return jsonify(treasure=treasure.name, proved=True, text="You already proved you were here.")
    data = request.get_json(silent=True) or {}
    used = set(db.session.execute(db.select(BoxProof.counter).filter_by(box_id=box.id)).scalars())
    counter, problem = check_code(box.secret, data.get("code") if isinstance(data, dict) else None, _now(), used)
    if problem:
        return jsonify(error=problem), 409 if problem == CODE_USED else 400
    db.session.add(BoxProof(box_id=box.id, user_id=me.id, counter=counter))
    try:
        db.session.commit()
    except IntegrityError:  # a double tap, or two players typed the same code at the same moment
        db.session.rollback()
        if not _proved(box.id, me.id):
            return jsonify(error=CODE_USED), 409
    return jsonify(treasure=treasure.name, proved=True,
                   text=f"Proved! You were really at {treasure.name}. Now find it on the map.")

"""QR collectibles: set one up, scan it, and see your 3D trophies (owner: A).

Rules live in collectibles.py, the 3D trophies are made by voxel_models.py.

Pages:  /collection (your trophies + set up your treasures), /scan (camera), /collect/<code>
        (what the printed QR code opens), /treasures/<id>/qr (the QR code to print).
API:    POST /api/collect {"code"}, GET /api/collection,
        POST /api/treasures/<id>/collect-here {"lat", "lon"} (collect it by walking there),
        POST /api/treasures/<id>/collectible (form: name, trophy, optional file "model"),
        GET /api/collectibles/<id>/model.glb

Tables collectibles and collected_items are new, so an existing geohunt.db gets them by itself.
"""

import io
import os
from datetime import datetime, timezone

import qrcode
import qrcode.image.svg
from flask import (Blueprint, current_app, jsonify, redirect, render_template, request,
                   send_file, url_for)
from sqlalchemy.exc import IntegrityError

from admin_api import is_admin
from auth_api import current_user
from collectibles import (can_manage, check_glb, clean_code, make_code, parse_name, parse_trophy,
                          still_to_find, utc_iso)
from location import FOUND_RADIUS_M, haversine_m
from models import Treasure, db
from treasure_input import parse_number

collectible_api = Blueprint("collectible_api", __name__)


class Collectible(db.Model):
    """A treasure's trophy and the secret code printed as a QR sticker at the spot."""

    __tablename__ = "collectibles"
    id = db.Column(db.Integer, primary_key=True)
    treasure_id = db.Column(db.Integer, db.ForeignKey("treasures.id"), nullable=False, unique=True)
    code = db.Column(db.String(16), nullable=False, unique=True)
    name = db.Column(db.String(40), nullable=False)
    trophy = db.Column(db.String(30), nullable=False, default="trophy")  # built-in look (also the 2D picture)
    uploaded = db.Column(db.Boolean, nullable=False, default=False)      # the player's own .glb model
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))


class CollectedItem(db.Model):
    """A player collected a trophy. Once each."""

    __tablename__ = "collected_items"
    __table_args__ = (db.UniqueConstraint("user_id", "collectible_id", name="collect_once"),)
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    collectible_id = db.Column(db.Integer, db.ForeignKey("collectibles.id"), nullable=False)
    collected_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))


# ------------------------------------------------------------ helpers


def _models_folder():
    return os.path.join(current_app.instance_path, "models")


def _upload_path(collectible_id):
    return os.path.join(_models_folder(), f"{collectible_id}.glb")


def model_url(c):
    return url_for("collectible_api.model_file", collectible_id=c.id)


def _item_dict(c, treasure_name=None):
    return {"id": c.id, "name": c.name, "trophy": c.trophy, "uploaded": c.uploaded,
            "model_url": model_url(c), "treasure": treasure_name}


def collectible_flags(user_id):
    """For the map: {treasure_id: True/False (collected by this player)} for every treasure
    that has a collectible. Two small queries."""
    rows = db.session.execute(db.select(Collectible.id, Collectible.treasure_id)).all()
    mine = set()
    if user_id is not None:
        mine = set(db.session.execute(db.select(CollectedItem.collectible_id)
                                      .where(CollectedItem.user_id == user_id)).scalars().all())
    return {tid: cid in mine for cid, tid in rows}


def collect(user, code):
    """Give the player the trophy behind this code. Returns (collectible, is_new) or raises ValueError."""
    c = db.session.execute(db.select(Collectible).where(Collectible.code == code)).scalar_one_or_none()
    if c is None:
        raise ValueError("No collectible has this code")
    return give(user, c)


def give(user, c):
    """Add collectible c to the player's shelf (once). Returns (c, is_new) or raises ValueError.
    Used by both ways of collecting: scanning the QR code and walking to the treasure."""
    treasure = db.session.get(Treasure, c.treasure_id)
    if treasure is not None and treasure.created_by == user.id:
        raise ValueError("You hid this treasure yourself, so you can't collect its trophy")
    done = db.session.execute(db.select(CollectedItem).where(
        CollectedItem.user_id == user.id, CollectedItem.collectible_id == c.id)).scalar_one_or_none()
    if done is not None:
        return c, False
    db.session.add(CollectedItem(user_id=user.id, collectible_id=c.id))
    try:
        db.session.commit()
    except IntegrityError:  # a double scan: the other request saved it a moment ago
        db.session.rollback()
        return c, False
    return c, True


# ------------------------------------------------------------ pages


@collectible_api.route("/collection")
def collection_page():
    if current_user() is None:
        return redirect(url_for("auth_api.login_page", next=request.full_path.rstrip("?")))
    return render_template("collection.html")


@collectible_api.route("/scan")
def scan_page():
    if current_user() is None:
        return redirect(url_for("auth_api.login_page", next="/scan"))
    return render_template("scan.html")


@collectible_api.route("/collect/<code>")
def collect_link(code):
    """What the printed QR code opens (a phone's normal camera app works too)."""
    user = current_user()
    if user is None:
        return redirect(url_for("auth_api.login_page", next=request.path))
    try:
        c, is_new = collect(user, clean_code(code))
    except ValueError as err:
        return redirect(url_for("collectible_api.collection_page", error=str(err)))
    return redirect(url_for("collectible_api.collection_page", new=c.id if is_new else None, have=c.id))


@collectible_api.route("/treasures/<int:treasure_id>/qr")
def qr_page(treasure_id):
    """The QR code to print and stick at the treasure. Only whoever hid it (or an admin)."""
    user = current_user()
    if user is None:
        return redirect(url_for("auth_api.login_page", next=request.path))
    treasure = db.session.get(Treasure, treasure_id)
    c = db.session.execute(db.select(Collectible).where(Collectible.treasure_id == treasure_id)).scalar_one_or_none()
    if treasure is None or c is None:
        return "This treasure has no collectible yet.", 404
    if not can_manage(user.id, treasure.created_by, is_admin(user)):
        return "Only the player who hid this treasure can print its QR code.", 403
    link = request.host_url.rstrip("/") + url_for("collectible_api.collect_link", code=c.code)
    return render_template("qr.html", treasure=treasure, collectible=c, link=link,
                           svg=qr_svg(link))


def qr_svg(text):
    """The QR code for this text as an SVG picture (Python makes it with the qrcode library)."""
    image = qrcode.make(text, image_factory=qrcode.image.svg.SvgPathImage, box_size=12, border=2)
    out = io.BytesIO()
    image.save(out)
    return out.getvalue().decode("utf-8")


# ------------------------------------------------------------ API


@collectible_api.route("/api/collect", methods=["POST"])
def api_collect():
    user = current_user()
    if user is None:
        return jsonify(error="Log in first"), 401
    data = request.get_json(silent=True)
    try:
        c, is_new = collect(user, clean_code(data.get("code") if isinstance(data, dict) else None))
    except ValueError as err:
        return jsonify(error=str(err)), 400
    treasure = db.session.get(Treasure, c.treasure_id)
    return jsonify(new=is_new, item=_item_dict(c, treasure.name if treasure else None))


@collectible_api.route("/api/treasures/<int:treasure_id>/collect-here", methods=["POST"])
def collect_here(treasure_id):
    """Collect a treasure's trophy by standing at it (the map calls this when you arrive).

    The phone only says where it is: Python checks you are within FOUND_RADIUS_M (20 m),
    the same rule that pays the coins. Scanning the QR code still works too.
    """
    user = current_user()
    if user is None:
        return jsonify(error="Log in first"), 401
    treasure = db.session.get(Treasure, treasure_id)
    if treasure is None:
        return jsonify(error="No such treasure"), 404
    c = db.session.execute(db.select(Collectible).where(Collectible.treasure_id == treasure_id)).scalar_one_or_none()
    if c is None:
        return jsonify(error="This treasure has no collectible"), 404

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error="Send your lat and lon"), 400
    try:
        lat = parse_number(data.get("lat"), "lat", -90, 90)
        lon = parse_number(data.get("lon"), "lon", -180, 180)
    except ValueError as err:
        return jsonify(error=str(err)), 400
    distance_m = haversine_m(lat, lon, treasure.lat, treasure.lon)
    if distance_m > FOUND_RADIUS_M:
        return jsonify(error=f"You are {round(distance_m)} m away. Get within {FOUND_RADIUS_M} m.",
                       distance_m=round(distance_m, 1)), 400

    try:
        c, is_new = give(user, c)
    except ValueError as err:
        return jsonify(error=str(err)), 403
    return jsonify(new=is_new, item=_item_dict(c, treasure.name))


@collectible_api.route("/api/collection")
def api_collection():
    """Your trophies, and the treasures you hid (to set up their collectible)."""
    user = current_user()
    if user is None:
        return jsonify(error="Log in first"), 401
    rows = db.session.execute(
        db.select(Collectible, CollectedItem.collected_at, Treasure)
        .join(CollectedItem, CollectedItem.collectible_id == Collectible.id)
        .join(Treasure, Treasure.id == Collectible.treasure_id, isouter=True)
        .where(CollectedItem.user_id == user.id).order_by(CollectedItem.id.desc())).all()
    # Each trophy also says where it was found, for the shelf's "where and when" card.
    mine = [dict(_item_dict(c, t.name if t else None), collected_at=utc_iso(when),
                 lat=t.lat if t else None, lon=t.lon if t else None) for c, when, t in rows]
    total = db.session.execute(db.select(db.func.count(Collectible.id))).scalar()
    hidden_by_me = db.session.execute(
        db.select(db.func.count(Collectible.id)).join(Treasure, Treasure.id == Collectible.treasure_id)
        .where(Treasure.created_by == user.id)).scalar()

    admin = is_admin(user)
    query = db.select(Treasure).order_by(Treasure.id)
    if not admin:
        query = query.where(Treasure.created_by == user.id)
    hidden = []
    for t in db.session.execute(query).scalars().all():
        c = db.session.execute(db.select(Collectible).where(Collectible.treasure_id == t.id)).scalar_one_or_none()
        hidden.append({"id": t.id, "name": t.name,
                       "collectible": dict(_item_dict(c), code=c.code) if c else None})
    from voxel_models import TROPHIES  # the built-in looks to choose from
    return jsonify(mine=mine, my_treasures=hidden, trophies=TROPHIES, is_admin=admin,
                   to_find=still_to_find(total, hidden_by_me, len(mine)))


@collectible_api.route("/api/treasures/<int:treasure_id>/collectible", methods=["POST"])
def set_up_collectible(treasure_id):
    """Add (or change) a treasure's collectible. Form fields: name, trophy, and optionally
    a file "model" (.glb) the player made themselves. Keeps the same QR code when changing."""
    user = current_user()
    if user is None:
        return jsonify(error="Log in first"), 401
    treasure = db.session.get(Treasure, treasure_id)
    if treasure is None:
        return jsonify(error="No such treasure"), 404
    if not can_manage(user.id, treasure.created_by, is_admin(user)):
        return jsonify(error="Only the player who hid this treasure can set up its collectible."), 403

    data = request.form if request.form else (request.get_json(silent=True) or {})
    upload = request.files.get("model")
    try:
        trophy = parse_trophy(data.get("trophy"))
        name = parse_name(data.get("name"), f"{treasure.name} trophy")
        model_bytes = upload.read() if upload and upload.filename else None
        if model_bytes is not None:
            check_glb(model_bytes)
    except ValueError as err:
        return jsonify(error=str(err)), 400

    c = db.session.execute(db.select(Collectible).where(Collectible.treasure_id == treasure_id)).scalar_one_or_none()
    if c is None:
        c = Collectible(treasure_id=treasure_id, code=make_code(), created_by=user.id)
        db.session.add(c)
    c.name, c.trophy = name, trophy
    if model_bytes is not None:
        c.uploaded = True
    db.session.flush()  # gives a new collectible its id, for the file name
    if model_bytes is not None:
        os.makedirs(_models_folder(), exist_ok=True)
        with open(_upload_path(c.id), "wb") as f:
            f.write(model_bytes)
    db.session.commit()
    return jsonify(dict(_item_dict(c, treasure.name), code=c.code,
                        qr_page=url_for("collectible_api.qr_page", treasure_id=treasure_id))), 201


@collectible_api.route("/api/collectibles/<int:collectible_id>/model.glb")
def model_file(collectible_id):
    """The 3D model: the player's own upload if there is one, else our voxel trophy."""
    c = db.session.get(Collectible, collectible_id)
    if c is None:
        return jsonify(error="No such collectible"), 404
    if c.uploaded and os.path.exists(_upload_path(c.id)):
        return send_file(_upload_path(c.id), mimetype="model/gltf-binary")
    return redirect(url_for("static", filename=f"models/{c.trophy}.glb"))

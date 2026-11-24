"""Upload and list treasures (Feature 3, owner: B).

Like route_api.py, this lives in its own Blueprint. app.py only needs:

    from treasure_api import treasure_api
    app.register_blueprint(treasure_api)
"""

from flask import Blueprint, jsonify, render_template, request

from auth_api import current_user
from models import Treasure, db
from treasure_input import MIN_TREASURE_GAP_M, find_too_close, parse_treasure

treasure_api = Blueprint("treasure_api", __name__)


@treasure_api.route("/upload")
def upload_page():
    """The form where a player hides a new treasure."""
    return render_template("upload.html")


@treasure_api.route("/api/treasures", methods=["POST"])
def create_treasure():
    """Save a new treasure. Send JSON or form fields: name, description, lat, lon.

    Only logged-in players can hide treasures, and a treasure must be at least
    MIN_TREASURE_GAP_M from every other one.
    """
    user = current_user()
    if user is None:
        return jsonify(error="Log in to hide a treasure"), 401

    data = request.get_json(silent=True)
    if data is None:
        data = request.form.to_dict()

    try:
        clean = parse_treasure(data)
    except ValueError as err:
        return jsonify(error=str(err)), 400

    others = db.session.execute(db.select(Treasure.name, Treasure.lat, Treasure.lon)).all()
    nearby = find_too_close(clean["lat"], clean["lon"], others)
    if nearby is not None:
        return jsonify(error=f'"{nearby}" is already hidden within {MIN_TREASURE_GAP_M} m of '
                             "this spot. Choose a different place."), 409

    treasure = Treasure(**clean, created_by=user.id)
    db.session.add(treasure)
    db.session.commit()
    return jsonify(treasure.to_dict()), 201


@treasure_api.route("/api/treasures", methods=["GET"])
def list_treasures():
    """Return every saved treasure, oldest first.

    B: each one says found_by_me, so the map can show a tick on the ones you were already paid for.
    (Always False when you are logged out.)
    """
    from coin_api import current_values, found_treasure_ids  # here, not at the top, so the two files don't import each other

    query = db.select(Treasure).order_by(Treasure.id)
    treasures = db.session.execute(query).scalars().all()
    from rating_api import my_ratings, rating_summaries  # (same reason)

    user = current_user()
    found = set(found_treasure_ids(user.id)) if user else set()
    ratings = rating_summaries()
    mine = my_ratings(user.id) if user else {}
    none = {"average": None, "count": 0}
    from treasure_checks import verified_ids  # A: the admin's check mark (same reason)
    from collectible_api import collectible_flags  # A: QR collectibles (same reason)
    verified = verified_ids()
    collectibles = collectible_flags(user.id if user else None)
    values = current_values(treasures)  # B: what each pays right now (treasure_value.py)
    return jsonify([{**t.to_dict(), "found_by_me": t.id in found,
                     "value": values[t.id],
                     "verified": t.id in verified,  # A: checked by an admin (demo ones always are)
                     "collectible": t.id in collectibles,  # A: has a QR trophy at the spot
                     "collected_by_me": collectibles.get(t.id, False),
                     # B: stars for the map's info board (see ratings.py)
                     "rating": {k: ratings.get(t.id, none)[k] for k in ("average", "count")},
                     "my_rating": mine.get(t.id)} for t in treasures])

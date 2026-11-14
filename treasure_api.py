"""Upload and list treasures (Feature 3, owner: B).

Like route_api.py, this lives in its own Blueprint. app.py only needs:

    from treasure_api import treasure_api
    app.register_blueprint(treasure_api)
"""

from flask import Blueprint, jsonify, render_template, request

from auth_api import current_user
from models import Treasure, db
from treasure_input import parse_number, parse_treasure, spot_problem

treasure_api = Blueprint("treasure_api", __name__)


@treasure_api.route("/upload")
def upload_page():
    """The form where a player hides a new treasure."""
    return render_template("upload.html")


def _all_spots():
    """(name, lat, lon) of every treasure, for the 10 m check."""
    return db.session.execute(db.select(Treasure.name, Treasure.lat, Treasure.lon)).all()


@treasure_api.route("/api/treasures/spot")
def check_spot():
    """Can a treasure go here? GET /api/treasures/spot?lat=..&lon=..

    The upload page asks this when a spot is tapped on the map, so the player
    knows straight away. Python decides; the page only shows the answer.
    """
    try:
        lat = parse_number(request.args.get("lat"), "lat", -90, 90)
        lon = parse_number(request.args.get("lon"), "lon", -180, 180)
    except ValueError as err:
        return jsonify(error=str(err)), 400
    problem = spot_problem(lat, lon, _all_spots())
    return jsonify(ok=problem is None, lat=round(lat, 6), lon=round(lon, 6),
                   message=problem or "This spot is free. Give it a name and hide it!")


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

    problem = spot_problem(clean["lat"], clean["lon"], _all_spots())
    if problem is not None:
        return jsonify(error=problem), 409

    treasure = Treasure(**clean, created_by=user.id)
    db.session.add(treasure)
    db.session.commit()
    return jsonify(treasure.to_dict()), 201


@treasure_api.route("/api/treasures", methods=["GET"])
def list_treasures():
    """Return every saved treasure, oldest first."""
    query = db.select(Treasure).order_by(Treasure.id)
    treasures = db.session.execute(query).scalars().all()
    return jsonify([t.to_dict() for t in treasures])

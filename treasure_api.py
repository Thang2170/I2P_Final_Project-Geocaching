"""Upload and list treasures (Feature 3, owner: B).

Like route_api.py, this lives in its own Blueprint. app.py only needs:

    from treasure_api import treasure_api
    app.register_blueprint(treasure_api)
"""

from flask import Blueprint, jsonify, render_template, request

from models import Treasure, db
from treasure_input import parse_treasure

treasure_api = Blueprint("treasure_api", __name__)


@treasure_api.route("/upload")
def upload_page():
    """The form where a player hides a new treasure."""
    return render_template("upload.html")


@treasure_api.route("/api/treasures", methods=["POST"])
def create_treasure():
    """Save a new treasure. Send JSON or form fields: name, description, lat, lon."""
    data = request.get_json(silent=True)
    if data is None:
        data = request.form.to_dict()

    try:
        clean = parse_treasure(data)
    except ValueError as err:
        return jsonify(error=str(err)), 400

    treasure = Treasure(**clean)
    db.session.add(treasure)
    db.session.commit()
    return jsonify(treasure.to_dict()), 201


@treasure_api.route("/api/treasures", methods=["GET"])
def list_treasures():
    """Return every saved treasure, oldest first."""
    query = db.select(Treasure).order_by(Treasure.id)
    treasures = db.session.execute(query).scalars().all()
    return jsonify([t.to_dict() for t in treasures])

"""Eyes-free mode (owner: B). Rules: guide.py.

- GET /eyes-free                                          the page
- GET /api/guide/<treasure_id>?lat=..&lon=..&heading=..   how fast to beep, how to buzz, what to say
  (heading: the way the phone faces, 0 to 360; leave it out if the phone has no compass)
"""

from flask import Blueprint, jsonify, redirect, render_template, request

from auth_api import current_user
from guide import BUZZ_HELP, bearing_deg, guide
from location import haversine_m
from models import Treasure, db
from play_input import parse_position
from treasure_input import parse_number

guide_api = Blueprint("guide_api", __name__)


@guide_api.route("/eyes-free")
def eyes_free_page():
    if current_user() is None:
        return redirect("/login?next=/eyes-free")
    return render_template("eyes_free.html", buzz_help=BUZZ_HELP)


@guide_api.route("/api/guide/<int:treasure_id>")
def guide_api_view(treasure_id):
    me = current_user()
    if me is None:
        return jsonify(error="Log in first"), 401
    treasure = db.session.get(Treasure, treasure_id)
    from condition_api import conditions_by_id, hidden_ids  # rain and night treasures stay hidden here too
    if treasure is None or treasure.id in hidden_ids([treasure], me.id, conditions_by_id()):
        return jsonify(error="No such treasure"), 404
    try:
        lat, lon = parse_position(request.args.to_dict())
        raw = request.args.get("heading", "")
        heading = parse_number(raw, "heading", 0, 360) if raw.strip() else None
    except ValueError as err:
        return jsonify(error=str(err)), 400
    distance = haversine_m(lat, lon, treasure.lat, treasure.lon)
    return jsonify(guide(treasure.name, distance, bearing_deg(lat, lon, treasure.lat, treasure.lon), heading)
                   | {"treasure": treasure.name})

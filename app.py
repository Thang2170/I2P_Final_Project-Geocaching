import os

from flask import Flask, jsonify, render_template, request

from location import FOUND_RADIUS_M, haversine_m
from models import Treasure, db, seed_demo_data

from auth_api import auth_api
from route_api import route_api
from treasure_api import treasure_api


app = Flask(__name__)
app.register_blueprint(route_api)
app.register_blueprint(treasure_api)
app.register_blueprint(auth_api)
# Login sessions are signed with this key. For the real deployment, set a SECRET_KEY
# environment variable (never commit a real key); the fallback is for local testing only.
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-only-change-me")
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
# SQLite database file. Flask puts it in a folder called "instance".
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///geohunt.db"
db.init_app(app)

# Create the tables (if missing) and save the demo treasure on the first run.
with app.app_context():
    db.create_all()
    seed_demo_data()


def get_current_treasure():
    """Return the treasure the map shows: the first one in the database."""
    query = db.select(Treasure).order_by(Treasure.id)
    return db.session.execute(query).scalars().first()


@app.route("/")
def home():
    treasure = get_current_treasure()
    if treasure is None:
        return "No treasures in the database yet.", 404
    return render_template("map.html", treasure=treasure.to_dict())


@app.route("/api/distance")
def distance():
    try:
        lat = float(request.args["lat"])
        lon = float(request.args["lon"])
    except (KeyError, ValueError):
        return jsonify(error="Need numeric lat and lon"), 400

    treasure = get_current_treasure()
    if treasure is None:
        return jsonify(error="No treasures in the database yet"), 404

    meters = haversine_m(lat, lon, treasure.lat, treasure.lon)
    return jsonify(treasure=treasure.name, meters=round(meters, 1), found = meters <= FOUND_RADIUS_M)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True, ssl_context="adhoc")

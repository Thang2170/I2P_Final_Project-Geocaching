import os

from flask import Flask, jsonify, redirect, render_template, request, url_for

from location import FOUND_RADIUS_M, haversine_m
from models import Treasure, db, seed_demo_data

from auth_api import auth_api, current_user
from route_api import route_api
from treasure_api import treasure_api
from walk_api import walk_api


def get_current_treasure():
    """Return the treasure the map shows: the first one in the database."""
    query = db.select(Treasure).order_by(Treasure.id)
    return db.session.execute(query).scalars().first()


def create_app(database_uri="sqlite:///geohunt.db"):
    """Build the Flask app.

    The default database is a file in the "instance" folder. Tests pass
    "sqlite:///:memory:" so they get a fresh, throwaway database and never touch
    a real one.
    """
    app = Flask(__name__)
    app.register_blueprint(route_api)
    app.register_blueprint(treasure_api)
    app.register_blueprint(auth_api)
    app.register_blueprint(walk_api)
    # Login sessions are signed with this key. For the real deployment, set a SECRET_KEY
    # environment variable (never commit a real key); the fallback is for local testing only.
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-only-change-me")
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SQLALCHEMY_DATABASE_URI"] = database_uri
    db.init_app(app)

    # Create the tables (if missing) and save the demo treasure on the first run.
    with app.app_context():
        db.create_all()
        seed_demo_data()

    @app.route("/")
    def home():
        # A: the map is for logged-in players, so send everyone else to the login page first.
        # "next" remembers the full address (e.g. /?drag) so login can bring them back to it.
        if current_user() is None:
            return redirect(url_for("auth_api.login_page", next=request.full_path.rstrip("?")))

        treasure = get_current_treasure()
        if treasure is None:
            return "No treasures in the database yet.", 404
        return render_template("map.html", treasure=treasure.to_dict())

    @app.route("/welcome")
    def welcome():
        """C's landing page that introduces the app. Anyone can see it."""
        return render_template("index.html")

    @app.route("/api/distance")
    def distance():
        try:
            lat = float(request.args["lat"])
            lon = float(request.args["lon"])
        except (KeyError, ValueError):
            return jsonify(error="Need numeric lat and lon"), 400

        # Optional treasure_id: measure to the treasure the player tapped on the map.
        # Without it we keep the old behaviour (the first treasure).
        treasure_id = request.args.get("treasure_id")
        if treasure_id is None:
            treasure = get_current_treasure()
        else:
            try:
                treasure = db.session.get(Treasure, int(treasure_id))
            except ValueError:
                return jsonify(error="treasure_id must be a whole number"), 400

        if treasure is None:
            return jsonify(error="No such treasure"), 404

        meters = haversine_m(lat, lon, treasure.lat, treasure.lon)
        return jsonify(treasure=treasure.name, meters=round(meters, 1), found=meters <= FOUND_RADIUS_M)

    return app


# The app that "python app.py" runs, and that the page tests import.
app = create_app()


if __name__ == "__main__":
    # Debug mode lets anyone who can reach the page run code on this computer, and
    # host 0.0.0.0 lets the whole Wi-Fi reach it. So debug is OFF unless you ask:
    #   $env:FLASK_DEBUG = "1"; python app.py
    debug = os.environ.get("FLASK_DEBUG") == "1"
    app.run(host="0.0.0.0", port=5000, debug=debug, ssl_context="adhoc")

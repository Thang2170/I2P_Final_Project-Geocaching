import os

from flask import Flask, jsonify, redirect, render_template, request, url_for

from location import FOUND_RADIUS_M, haversine_m
from models import Treasure, db, seed_demo_data, seed_demo_hunt

from admin_api import admin_api
from auth_api import auth_api, current_user
from chat_api import chat_api
from coin_api import coin_api, found_treasure_ids
from coins import first_to_find
from feed_api import feed_api
from hunt_api import hunt_api
from hunt_game_api import hunt_game_api  # A: hunt races
from journey_resume_api import journey_resume_api  # A: carry on after losing signal
from collectible_api import collectible_api  # A: QR collectibles and 3D trophies
from health_api import health_api  # A: the ESP32 wearable and its health summary
from journey_api import journey_api
from leaderboard_api import leaderboard_api
from notify_api import notify_api
from onboarding_api import onboarding_api
from photo_api import photo_api
from profile_api import profile_api
from rate_limit import MIN_GAP_S
from friends_api import friends_api
from rating_api import rating_api
from route_api import route_api
from secret_key import KEY_FILE, choose_secret_key, new_key
from shop_api import shop_api
from challenge_api import challenge_api
from pwa_api import pwa_api
from riddle_api import riddle_api
from territory_api import territory_api
from zone_api import zone_api
from goal_api import goal_api
from weather_api import weather_api
from mode_api import mode_api
from safety_api import safety_api
from habit_api import habit_api
from journey_live_api import journey_live_api
from privacy_api import privacy_api
from trail_api import trail_api
from treasure_api import treasure_api
from walk_api import walk_api
from walk_proof import parse_mode
from walk_proof_api import walk_proof_api


def get_current_treasure(user=None):
    """Return the treasure the map aims at first.

    B: for a logged-in player, the oldest treasure they haven't found yet (see coins.first_to_find);
    otherwise the first one in the database.
    """
    ids = db.session.execute(db.select(Treasure.id).order_by(Treasure.id)).scalars().all()
    user_id = getattr(user, "id", None)  # some page tests log in with a stand-in object that has no id
    found = found_treasure_ids(user_id) if user_id is not None else []
    target = first_to_find(ids, found)
    return db.session.get(Treasure, target) if target is not None else None


def _secret_key(app, database_uri):
    """SECRET_KEY from the environment, or a random one kept in instance/secret_key."""
    if database_uri.startswith("sqlite:///:memory:"):
        return new_key()  # tests: a throwaway key, and no file written
    path = os.path.join(app.instance_path, KEY_FILE)
    try:
        with open(path, encoding="utf-8") as f:
            saved = f.read()
    except FileNotFoundError:
        saved = None
    key, must_save = choose_secret_key(os.environ.get("SECRET_KEY"), saved)
    if must_save:
        os.makedirs(app.instance_path, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(key)
    return key


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
    app.register_blueprint(coin_api)
    app.register_blueprint(shop_api)
    app.register_blueprint(hunt_api)
    app.register_blueprint(hunt_game_api)
    app.register_blueprint(journey_resume_api)
    app.register_blueprint(collectible_api)
    app.register_blueprint(health_api)
    app.register_blueprint(chat_api)
    app.register_blueprint(notify_api)
    app.register_blueprint(rating_api)
    app.register_blueprint(friends_api)
    app.register_blueprint(profile_api)
    app.register_blueprint(journey_api)
    app.register_blueprint(feed_api)
    app.register_blueprint(photo_api)
    app.register_blueprint(leaderboard_api)
    app.register_blueprint(admin_api)
    app.register_blueprint(onboarding_api)
    app.register_blueprint(trail_api)  # B: Treasure Trail loops (trail_planner.py)
    app.register_blueprint(walk_proof_api)  # B: prove you walked (walk_proof.py)
    app.register_blueprint(riddle_api)  # B: riddle chains (riddles.py)
    app.register_blueprint(challenge_api)  # B: streaks and weekly challenges (streaks.py)
    app.register_blueprint(pwa_api)  # B: install as an app (manifest, service worker)
    app.register_blueprint(territory_api)  # B: claim the campus (territory.py)
    app.register_blueprint(zone_api)  # B: heart-rate zone coach (zone_coach.py)
    app.register_blueprint(goal_api)  # B: health goals and milestones (goals.py)
    app.register_blueprint(weather_api)  # B: weather-aware routes (weather.py)
    app.register_blueprint(mode_api)  # B: try-hard and calm walks (modes.py)
    app.register_blueprint(safety_api)  # B: safety alerts from the band (safety.py)
    app.register_blueprint(habit_api)  # B: daily ring, streak freezes, sharing (habits.py)
    app.register_blueprint(journey_live_api)  # B: one live update while you walk
    app.register_blueprint(privacy_api)  # B: download my data, delete my band data (privacy.py)
    # B: login cookies are signed with this key. It is never a fixed text in the code any more
    # (anyone could read that in the repo); see secret_key.py.
    app.config["SECRET_KEY"] = _secret_key(app, database_uri)
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SQLALCHEMY_DATABASE_URI"] = database_uri
    # B: the anti-spam waits (rate_limit.py). Tests use a throwaway in-memory database and post
    # many things quickly, so there the waits are off; tests of the waits switch them back on.
    testing = database_uri.startswith("sqlite:///:memory:")
    app.config["SPAM_GAPS"] = {kind: 0 for kind in MIN_GAP_S} if testing else dict(MIN_GAP_S)
    # B: prove you walked. "flag" (default): suspicious finds are paid and listed for an admin.
    # "block": they are refused. Set with the STEPQUEST_WALK_PROOF environment variable.
    app.config["WALK_PROOF"] = parse_mode(os.environ.get("STEPQUEST_WALK_PROOF"))
    # B: weather-aware routes (weather.py) ask Open-Meteo. Off in tests (they never call it),
    # and off if STEPQUEST_WEATHER=off.
    app.config["WEATHER"] = not testing and os.environ.get("STEPQUEST_WEATHER", "on").lower() != "off"
    db.init_app(app)

    # Create the tables (if missing) and save the demo treasure on the first run.
    with app.app_context():
        db.create_all()
        seed_demo_data()
        seed_demo_hunt()

    @app.route("/")
    def home():
        # A: the map is for logged-in players, so send everyone else to the login page first.
        # "next" remembers the full address (e.g. /?drag) so login can bring them back to it.
        user = current_user()
        if user is None:
            return redirect(url_for("auth_api.login_page", next=request.full_path.rstrip("?")))

        treasure = get_current_treasure(user)
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

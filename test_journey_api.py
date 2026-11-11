import unittest

from flask import Flask

from auth_api import auth_api
from journey_api import journey_api
from models import Journey, Treasure, User, db
from walk_api import walk_api

LAT, LON = 24.795324, 120.994796


class TestJourneyApi(unittest.TestCase):
    def setUp(self):
        # A throwaway app with an in-memory database, so tests never touch geohunt.db.
        self.app = Flask(__name__)
        self.app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
        self.app.config["SECRET_KEY"] = "test-key"
        db.init_app(self.app)
        for blueprint in (auth_api, walk_api, journey_api):
            self.app.register_blueprint(blueprint)
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
        self.context.pop()

    def player(self, name):
        client = self.app.test_client()
        client.post("/api/register", json={"username": name, "password": "secret1"})
        return client

    def treasure(self, name="Pond", creator=None, lat=LAT, lon=LON):
        owner = db.session.query(User).filter_by(username=creator).one() if creator else None
        treasure = Treasure(name=name, lat=lat, lon=lon, creator=owner)
        db.session.add(treasure)
        db.session.commit()
        return treasure.id

    def body(self, treasure_id, **changes):
        data = {"treasure_id": treasure_id, "distance_m": 750, "duration_s": 600, "lat": LAT, "lon": LON}
        data.update(changes)
        return data

    def save(self, client, treasure_id, **changes):
        return client.post("/api/journeys", json=self.body(treasure_id, **changes))

    def save_raw(self, client, body):
        """Send exactly this body (used to try a bad treasure_id)."""
        return client.post("/api/journeys", json=body)

    # ---------------------------------------------------------------- pages

    def test_community_page_loads(self):
        r = self.app.test_client().get("/community")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"Community", r.data)

    # ---------------------------------------------------------------- saving

    def test_saving_needs_a_login(self):
        tid = self.treasure()
        r = self.save(self.app.test_client(), tid)
        self.assertEqual(r.status_code, 401)

    def test_saves_a_finished_hunt(self):
        tid = self.treasure("Pond")
        r = self.save(self.player("ann"), tid)
        self.assertEqual(r.status_code, 201)
        data = r.get_json()
        self.assertEqual((data["treasure"], data["distance_km"], data["time"]), ("Pond", 0.75, "10:00"))
        self.assertEqual(data["pace"], "13:20")
        self.assertEqual(db.session.query(Journey).count(), 1)

    def test_steps_and_calories_come_from_python_with_the_default_weight(self):
        tid = self.treasure()
        data = self.save(self.player("ann"), tid).get_json()
        self.assertEqual(data["steps"], 1000)        # 750 m / 0.75 m per step
        self.assertEqual(data["calories"], 24.4)     # 0.5 * 65 kg (default) * 0.75 km

    def test_calories_use_the_saved_weight(self):
        tid = self.treasure()
        ann = self.player("ann")
        ann.post("/api/me/weight", json={"weight_kg": 80})
        self.assertEqual(self.save(ann, tid).get_json()["calories"], 30.0)

    def test_numbers_sent_by_the_browser_for_steps_and_calories_are_ignored(self):
        tid = self.treasure()
        data = self.save(self.player("ann"), tid, steps=999999, calories=999999).get_json()
        self.assertEqual((data["steps"], data["calories"]), (1000, 24.4))

    def test_bad_numbers_are_rejected(self):
        tid = self.treasure()
        ann = self.player("ann")
        for changes in ({"distance_m": -5}, {"duration_s": 0}, {"lat": 95}, {"distance_m": "far"}, {"treasure_id": "x"}):
            with self.subTest(changes=changes):
                self.assertEqual(self.save_raw(ann, {**self.body(tid), **changes}).status_code, 400)
        self.assertEqual(ann.post("/api/journeys", data="not json", content_type="text/plain").status_code, 400)
        self.assertEqual(db.session.query(Journey).count(), 0)

    def test_unknown_treasure_is_404(self):
        self.assertEqual(self.save(self.player("ann"), 999).status_code, 404)

    def test_your_own_treasure_is_not_saved(self):
        ann = self.player("ann")
        tid = self.treasure(creator="ann")
        r = self.save(ann, tid)
        self.assertEqual(r.status_code, 403)
        self.assertEqual(db.session.query(Journey).count(), 0)

    def test_you_must_be_at_the_treasure(self):
        tid = self.treasure()
        r = self.save(self.player("ann"), tid, lat=LAT + 0.001)      # about 111 m away
        self.assertEqual(r.status_code, 400)
        self.assertIn("m from the treasure", r.get_json()["error"])
        self.assertEqual(db.session.query(Journey).count(), 0)

    def test_a_car_ride_is_not_saved(self):
        tid = self.treasure()
        r = self.save(self.player("ann"), tid, distance_m=5000, duration_s=200)
        self.assertEqual(r.status_code, 400)
        self.assertIn("too fast", r.get_json()["error"])

    def test_the_same_hunt_cannot_be_saved_twice(self):
        tid = self.treasure()
        ann = self.player("ann")
        self.assertEqual(self.save(ann, tid).status_code, 201)
        self.assertEqual(self.save(ann, tid).status_code, 409)
        self.assertEqual(db.session.query(Journey).count(), 1)

    def test_two_players_can_each_save_the_same_treasure(self):
        tid = self.treasure()
        self.assertEqual(self.save(self.player("ann"), tid).status_code, 201)
        self.assertEqual(self.save(self.player("bob"), tid).status_code, 201)

    # ---------------------------------------------------------------- my hunts

    def test_my_hunts_need_a_login(self):
        self.assertEqual(self.app.test_client().get("/api/journeys/mine").status_code, 401)

    def test_my_hunts_start_empty(self):
        data = self.player("ann").get("/api/journeys/mine").get_json()
        self.assertEqual(data["journeys"], [])
        self.assertEqual(data["totals"], {"hunts": 0, "distance_km": 0, "steps": 0, "calories": 0})

    def test_my_hunts_list_only_mine_with_totals(self):
        a, b = self.treasure("A"), self.treasure("B", lat=LAT + 0.01)
        ann, bo = self.player("ann"), self.player("bob")
        self.save(ann, a)
        self.save(ann, b, lat=LAT + 0.01, distance_m=250, duration_s=300)
        self.save(bo, a)
        data = ann.get("/api/journeys/mine").get_json()
        self.assertEqual([j["treasure"] for j in data["journeys"]], ["B", "A"])      # newest first
        self.assertEqual(data["totals"]["hunts"], 2)
        self.assertEqual(data["totals"]["distance_km"], 1.0)
        self.assertEqual(data["totals"]["steps"], 1000 + 333)

    # ---------------------------------------------------------------- community

    def test_community_needs_a_login(self):
        self.assertEqual(self.app.test_client().get("/api/community").status_code, 401)

    def test_community_with_nobody_is_empty(self):
        data = self.player("ann").get("/api/community").get_json()
        self.assertEqual((data["leaderboard"], data["recent"], data["me"], data["players"]), ([], [], None, 0))

    def test_leaderboard_ranks_by_hunts_then_distance(self):
        a, b = self.treasure("A"), self.treasure("B", lat=LAT + 0.01)
        ann, bo, cy = self.player("ann"), self.player("bob"), self.player("cyd")
        self.save(ann, a, distance_m=500)
        self.save(bo, a, distance_m=900)
        self.save(bo, b, lat=LAT + 0.01, distance_m=100)
        self.save(cy, a, distance_m=2000, duration_s=2000)
        data = ann.get("/api/community").get_json()
        self.assertEqual([(p["rank"], p["username"], p["hunts"]) for p in data["leaderboard"]],
                         [(1, "bob", 2), (2, "cyd", 1), (3, "ann", 1)])
        self.assertEqual([p["is_me"] for p in data["leaderboard"]], [False, False, True])
        self.assertEqual(data["me"], {"rank": 3, "hunts": 1, "distance_km": 0.5})
        self.assertEqual(data["players"], 3)

    def test_recent_hunts_show_who_did_them_newest_first(self):
        a, b = self.treasure("A"), self.treasure("B", lat=LAT + 0.01)
        ann, bo = self.player("ann"), self.player("bob")
        self.save(ann, a)
        self.save(bo, b, lat=LAT + 0.01)
        recent = bo.get("/api/community").get_json()["recent"]
        self.assertEqual([(j["username"], j["treasure"]) for j in recent], [("bob", "B"), ("ann", "A")])

    def test_a_player_with_no_hunts_has_no_rank(self):
        tid = self.treasure()
        self.save(self.player("ann"), tid)
        data = self.player("bob").get("/api/community").get_json()
        self.assertIsNone(data["me"])
        self.assertEqual(len(data["leaderboard"]), 1)


if __name__ == "__main__":
    unittest.main()

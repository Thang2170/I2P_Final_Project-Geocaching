import unittest

from flask import Flask

from auth_api import auth_api
from hunt_api import hunt_api
from models import Hunt, HuntMember, db, seed_demo_hunt


class TestHuntApi(unittest.TestCase):
    def setUp(self):
        # A throwaway app with an in-memory database, so tests never touch geohunt.db.
        self.app = Flask(__name__)
        self.app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
        self.app.config["SECRET_KEY"] = "test-key"
        db.init_app(self.app)
        self.app.register_blueprint(auth_api)
        self.app.register_blueprint(hunt_api)
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

    def create(self, client, **fields):
        body = {"name": "Night walk", "description": "Bring a torch", "capacity": 2}
        body.update(fields)
        return client.post("/api/hunts", json=body)

    def test_hunts_page_loads(self):
        r = self.app.test_client().get("/hunts")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"Hunts", r.data)

    def test_list_is_public_and_starts_empty(self):
        r = self.app.test_client().get("/api/hunts")
        self.assertEqual((r.status_code, r.get_json()), (200, []))

    def test_creating_a_hunt_makes_you_the_first_player(self):
        bao = self.player("bao")
        r = self.create(bao)
        self.assertEqual(r.status_code, 201)
        data = r.get_json()
        self.assertEqual((data["name"], data["capacity"], data["playing"], data["waiting"]), ("Night walk", 2, 1, 0))
        self.assertEqual(data["me"], {"state": "playing", "position": 1})

    def test_creating_needs_a_login(self):
        r = self.create(self.app.test_client())
        self.assertEqual(r.status_code, 401)
        self.assertEqual(db.session.query(Hunt).count(), 0)

    def test_bad_hunts_are_refused(self):
        bao = self.player("bao")
        for fields in [{"name": ""}, {"capacity": 0}, {"capacity": 99}, {"capacity": "abc"}]:
            with self.subTest(fields=fields):
                self.assertEqual(self.create(bao, **fields).status_code, 400)
        self.assertEqual(db.session.query(Hunt).count(), 0)

    def test_joining_adds_a_player(self):
        hunt_id = self.create(self.player("bao")).get_json()["id"]
        lan = self.player("lan")
        r = lan.post(f"/api/hunts/{hunt_id}/join")
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertEqual((data["playing"], data["waiting"]), (2, 0))
        self.assertEqual(data["me"], {"state": "playing", "position": 2})

    def test_a_full_hunt_puts_new_players_in_line(self):
        hunt_id = self.create(self.player("bao"), capacity=2).get_json()["id"]
        self.player("lan").post(f"/api/hunts/{hunt_id}/join")
        third = self.player("minh")
        data = third.post(f"/api/hunts/{hunt_id}/join").get_json()
        self.assertEqual((data["playing"], data["waiting"]), (2, 1))
        self.assertEqual(data["me"], {"state": "waiting", "position": 1})

    def test_leaving_moves_the_next_player_up(self):
        bao = self.player("bao")
        hunt_id = self.create(bao, capacity=1).get_json()["id"]
        lan = self.player("lan")
        lan.post(f"/api/hunts/{hunt_id}/join")
        self.assertEqual(lan.get("/api/hunts").get_json()[0]["me"]["state"], "waiting")

        r = bao.post(f"/api/hunts/{hunt_id}/leave")
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(r.get_json()["me"])
        self.assertEqual(lan.get("/api/hunts").get_json()[0]["me"], {"state": "playing", "position": 1})

    def test_rejoining_goes_to_the_back_of_the_line(self):
        bao = self.player("bao")
        hunt_id = self.create(bao, capacity=1).get_json()["id"]
        lan = self.player("lan")
        lan.post(f"/api/hunts/{hunt_id}/join")
        bao.post(f"/api/hunts/{hunt_id}/leave")
        data = bao.post(f"/api/hunts/{hunt_id}/join").get_json()
        self.assertEqual(data["me"], {"state": "waiting", "position": 1})

    def test_joining_twice_is_refused(self):
        bao = self.player("bao")
        hunt_id = self.create(bao).get_json()["id"]
        self.assertEqual(bao.post(f"/api/hunts/{hunt_id}/join").status_code, 409)
        self.assertEqual(db.session.query(HuntMember).count(), 1)

    def test_leaving_a_hunt_you_are_not_in_is_refused(self):
        hunt_id = self.create(self.player("bao")).get_json()["id"]
        self.assertEqual(self.player("lan").post(f"/api/hunts/{hunt_id}/leave").status_code, 409)

    def test_unknown_hunt(self):
        bao = self.player("bao")
        self.assertEqual(bao.post("/api/hunts/999/join").status_code, 404)
        self.assertEqual(bao.post("/api/hunts/999/leave").status_code, 404)

    def test_joining_and_leaving_need_a_login(self):
        hunt_id = self.create(self.player("bao")).get_json()["id"]
        anonymous = self.app.test_client()
        self.assertEqual(anonymous.post(f"/api/hunts/{hunt_id}/join").status_code, 401)
        self.assertEqual(anonymous.post(f"/api/hunts/{hunt_id}/leave").status_code, 401)

    def test_everyone_sees_the_same_counts_but_their_own_status(self):
        bao = self.player("bao")
        hunt_id = self.create(bao, capacity=1).get_json()["id"]
        lan = self.player("lan")
        lan.post(f"/api/hunts/{hunt_id}/join")
        for client, state in [(bao, "playing"), (lan, "waiting")]:
            hunt = client.get("/api/hunts").get_json()[0]
            self.assertEqual((hunt["playing"], hunt["waiting"]), (1, 1))
            self.assertEqual(hunt["me"]["state"], state)
        self.assertIsNone(self.app.test_client().get("/api/hunts").get_json()[0]["me"])

    def test_newest_hunt_comes_first(self):
        bao = self.player("bao")
        self.create(bao, name="First")
        self.create(bao, name="Second")
        self.assertEqual([h["name"] for h in bao.get("/api/hunts").get_json()], ["Second", "First"])

    def test_demo_hunt_is_saved_once(self):
        seed_demo_hunt()
        seed_demo_hunt()
        self.assertEqual(db.session.query(Hunt).count(), 1)
        self.assertIsNone(db.session.query(Hunt).one().created_by)


if __name__ == "__main__":
    unittest.main()

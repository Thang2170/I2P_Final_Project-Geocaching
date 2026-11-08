import unittest

from flask import Flask

from auth_api import auth_api
from coin_api import coin_api, get_balance
from models import DEMO_TREASURE, CoinTransaction, Treasure, User, db
from treasure_api import treasure_api

LAT, LON = 24.79, 120.99  # where the test treasure is hidden


class TestCoinApi(unittest.TestCase):
    def setUp(self):
        # A throwaway app with an in-memory database, so tests never touch geohunt.db.
        self.app = Flask(__name__)
        self.app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
        self.app.config["SECRET_KEY"] = "test-key"
        db.init_app(self.app)
        for blueprint in (auth_api, treasure_api, coin_api):
            self.app.register_blueprint(blueprint)
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()

        # "owner" hides a treasure; "player" is who goes looking for it.
        self.owner = self.app.test_client()
        self.owner.post("/api/register", json={"username": "owner", "password": "secret1"})
        self.treasure_id = self.owner.post(
            "/api/treasures", json={"name": "Library", "lat": LAT, "lon": LON}).get_json()["id"]
        self.player = self.app.test_client()
        self.player.post("/api/register", json={"username": "player", "password": "secret2"})

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
        self.context.pop()

    def claim(self, client=None, treasure_id=None, lat=LAT, lon=LON):
        return (client or self.player).post(f"/api/treasures/{treasure_id or self.treasure_id}/claim",
                                            json={"lat": lat, "lon": lon})

    def test_finding_a_treasure_pays_coins(self):
        r = self.claim()
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertEqual((data["treasure"], data["coins_earned"], data["balance"]), ("Library", 10, 10))

    def test_claiming_needs_a_login(self):
        r = self.app.test_client().post(f"/api/treasures/{self.treasure_id}/claim", json={"lat": LAT, "lon": LON})
        self.assertEqual(r.status_code, 401)
        self.assertEqual(db.session.query(CoinTransaction).count(), 0)

    def test_unknown_treasure(self):
        self.assertEqual(self.claim(treasure_id=99999).status_code, 404)

    def test_too_far_pays_nothing(self):
        r = self.claim(lat=LAT + 0.001)  # about 111 m away
        self.assertEqual(r.status_code, 400)
        self.assertIn("m away", r.get_json()["error"])
        self.assertGreater(r.get_json()["distance_m"], 100)
        self.assertEqual(db.session.query(CoinTransaction).count(), 0)

    def test_inside_and_outside_the_twenty_meter_circle(self):
        # 0.00017 degrees of latitude is about 18.9 m; 0.00019 is about 21.1 m
        self.assertEqual(self.claim(lat=LAT + 0.00019).status_code, 400)
        self.assertEqual(self.claim(lat=LAT + 0.00017).status_code, 200)

    def test_a_treasure_pays_only_once(self):
        self.assertEqual(self.claim().status_code, 200)
        second = self.claim()
        self.assertEqual(second.status_code, 409)
        self.assertEqual(get_balance(db.session.query(User).filter_by(username="player").one().id), 10)

    def test_you_cannot_claim_your_own_treasure(self):
        r = self.claim(client=self.owner)
        self.assertEqual(r.status_code, 403)
        self.assertEqual(db.session.query(CoinTransaction).count(), 0)

    def test_the_demo_treasure_can_be_claimed(self):
        # the demo treasure has no creator; add it by hand because setUp already hid another one
        db.session.add(Treasure(**DEMO_TREASURE))
        db.session.commit()
        demo = db.session.query(Treasure).filter_by(created_by=None).one()
        r = self.claim(treasure_id=demo.id, lat=demo.lat, lon=demo.lon)
        self.assertEqual(r.status_code, 200)

    def test_bad_coordinates(self):
        for body in [{}, {"lat": "abc", "lon": LON}, {"lat": 95, "lon": LON}, {"lat": LAT}]:
            with self.subTest(body=body):
                r = self.player.post(f"/api/treasures/{self.treasure_id}/claim", json=body)
                self.assertEqual(r.status_code, 400)
        self.assertEqual(db.session.query(CoinTransaction).count(), 0)

    def test_balance_and_found_list(self):
        before = self.player.get("/api/coins").get_json()
        self.assertEqual((before["balance"], before["found_treasure_ids"]), (0, []))
        self.claim()
        after = self.player.get("/api/coins").get_json()
        self.assertEqual((after["balance"], after["found_treasure_ids"]), (10, [self.treasure_id]))

    def test_coins_need_a_login(self):
        self.assertEqual(self.app.test_client().get("/api/coins").status_code, 401)

    def test_each_player_has_their_own_balance(self):
        self.claim()
        self.assertEqual(self.owner.get("/api/coins").get_json()["balance"], 0)

    def test_two_players_can_both_find_the_same_treasure(self):
        third = self.app.test_client()
        third.post("/api/register", json={"username": "third", "password": "secret3"})
        self.assertEqual(self.claim().status_code, 200)
        self.assertEqual(self.claim(client=third).status_code, 200)

    def test_spending_lowers_the_balance(self):
        # the shop (next week) will add negative rows like this
        self.claim()
        player = db.session.query(User).filter_by(username="player").one()
        db.session.add(CoinTransaction(user_id=player.id, amount=-4, reason="shop"))
        db.session.commit()
        self.assertEqual(self.player.get("/api/coins").get_json()["balance"], 6)


if __name__ == "__main__":
    unittest.main()

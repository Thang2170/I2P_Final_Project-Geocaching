import unittest
from datetime import datetime, timedelta, timezone

from admin_api import PlayerPosition
from app import create_app
from coin_api import get_balance
from hunt_game import WIN_BONUS, WIN_REASON
from hunt_game_api import HuntGame
from models import CoinTransaction, Notification, Treasure, User, db

AT_TREASURE = {"lat": 24.795324, "lon": 120.994796}   # the demo treasure (NTHU)
FAR_AWAY = {"lat": 24.7955, "lon": 120.9965}           # about 173 m from it


class TestHuntGameApi(unittest.TestCase):
    def setUp(self):
        # The real app (demo treasure and demo hunt) on a throwaway database
        self.app = create_app("sqlite:///:memory:")
        self.context = self.app.app_context()
        self.context.push()
        self.pond = Treasure(name="Pond", description="", lat=24.7940, lon=120.9930)
        db.session.add(self.pond)
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
        self.context.pop()

    def player(self, name):
        client = self.app.test_client()
        client.post("/api/register", json={"username": name, "password": "secret1"})
        return client

    def user_id(self, name):
        return db.session.execute(db.select(User.id).filter_by(username=name)).scalar_one()

    def make_hunt(self, client, capacity=1, treasure_id=None):
        body = {"name": "Solo race", "capacity": capacity}
        if treasure_id is not None:
            body["treasure_id"] = treasure_id
        return client.post("/api/hunts", json=body).get_json()

    # ------------------------------------------------ where the hunt goes

    def test_new_hunt_goes_to_the_chosen_treasure(self):
        hunt = self.make_hunt(self.player("bao"), treasure_id=self.pond.id)
        self.assertEqual(hunt["game"]["treasure"]["name"], "Pond")
        self.assertEqual(hunt["game"]["state"], "open")

    def test_without_a_choice_it_goes_to_the_first_treasure(self):
        hunt = self.make_hunt(self.player("bao"))
        self.assertEqual(hunt["game"]["treasure"]["name"], "National Tsing Hua University")

    def test_bad_treasure_is_refused(self):
        bao = self.player("bao")
        for value in ["abc", 9999]:
            with self.subTest(value=value):
                r = bao.post("/api/hunts", json={"name": "x", "treasure_id": value})
                self.assertEqual(r.status_code, 400)

    def test_old_hunts_get_a_treasure_too(self):
        # The demo hunt was made by seed_demo_hunt, with no game row
        demo = self.player("bao").get("/api/hunts").get_json()[-1]
        self.assertEqual(demo["name"], "NTHU campus walk")
        self.assertEqual(demo["game"]["treasure"]["name"], "National Tsing Hua University")

    # ------------------------------------------------ start

    def test_creator_can_start_a_one_player_hunt(self):
        bao = self.player("bao")
        hunt = self.make_hunt(bao, capacity=1)
        self.assertTrue(hunt["game"]["can_start"])
        r = bao.post(f"/api/hunts/{hunt['id']}/start")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["state"], "started")

    def test_only_the_creator_can_start(self):
        bao, lan = self.player("bao"), self.player("lan")
        hunt = self.make_hunt(bao, capacity=5)
        lan.post(f"/api/hunts/{hunt['id']}/join")
        self.assertFalse(lan.get("/api/hunts").get_json()[0]["game"]["can_start"])
        self.assertEqual(lan.post(f"/api/hunts/{hunt['id']}/start").status_code, 409)

    def test_nobody_can_join_after_the_start(self):
        bao = self.player("bao")
        hunt = self.make_hunt(bao, capacity=5)
        bao.post(f"/api/hunts/{hunt['id']}/start")
        r = self.player("lan").post(f"/api/hunts/{hunt['id']}/join")
        self.assertEqual(r.status_code, 409)
        self.assertIn("already started", r.get_json()["error"])

    def test_start_needs_a_login(self):
        hunt = self.make_hunt(self.player("bao"))
        self.assertEqual(self.app.test_client().post(f"/api/hunts/{hunt['id']}/start").status_code, 401)

    # ------------------------------------------------ win

    def test_arriving_first_wins_the_bonus(self):
        bao = self.player("bao")
        hunt = self.make_hunt(bao)
        bao.post(f"/api/hunts/{hunt['id']}/start")
        r = bao.post(f"/api/hunts/{hunt['id']}/arrived", json=AT_TREASURE)
        data = r.get_json()
        self.assertEqual(r.status_code, 200)
        self.assertTrue(data["won"])
        self.assertEqual((data["state"], data["winner"], data["bonus"]), ("finished", "bao", WIN_BONUS))
        self.assertEqual(get_balance(self.user_id("bao")), WIN_BONUS)
        reasons = db.session.execute(db.select(CoinTransaction.reason)).scalars().all()
        self.assertEqual(reasons, [WIN_REASON])

    def test_cannot_win_from_far_away(self):
        bao = self.player("bao")
        hunt = self.make_hunt(bao)
        bao.post(f"/api/hunts/{hunt['id']}/start")
        r = bao.post(f"/api/hunts/{hunt['id']}/arrived", json=FAR_AWAY)
        self.assertEqual(r.status_code, 409)
        self.assertIn("m away", r.get_json()["error"])
        self.assertIsNone(db.session.get(HuntGame, hunt["id"]).winner_id)

    def test_cannot_win_before_the_start(self):
        bao = self.player("bao")
        hunt = self.make_hunt(bao)
        r = bao.post(f"/api/hunts/{hunt['id']}/arrived", json=AT_TREASURE)
        self.assertEqual(r.status_code, 409)

    def test_only_the_first_arrival_wins_and_the_others_are_told(self):
        bao, lan = self.player("bao"), self.player("lan")
        hunt = self.make_hunt(bao, capacity=2)
        lan.post(f"/api/hunts/{hunt['id']}/join")
        bao.post(f"/api/hunts/{hunt['id']}/start")
        self.assertTrue(lan.post(f"/api/hunts/{hunt['id']}/arrived", json=AT_TREASURE).get_json()["won"])
        late = bao.post(f"/api/hunts/{hunt['id']}/arrived", json=AT_TREASURE)
        self.assertEqual(late.status_code, 409)
        self.assertEqual(late.get_json()["winner"], "lan")
        # bao (the loser) got a bell notification; lan (the winner) did not
        told = db.session.execute(db.select(Notification.user_id).filter_by(kind="hunt_won")).scalars().all()
        self.assertEqual(told, [self.user_id("bao")])
        bell = bao.get("/api/notifications").get_json()
        self.assertIn('lan won the hunt "Solo race"', str(bell))

    def test_waiting_line_cannot_win(self):
        bao, lan = self.player("bao"), self.player("lan")
        hunt = self.make_hunt(bao, capacity=1)
        lan.post(f"/api/hunts/{hunt['id']}/join")  # waits in line
        bao.post(f"/api/hunts/{hunt['id']}/start")
        r = lan.post(f"/api/hunts/{hunt['id']}/arrived", json=AT_TREASURE)
        self.assertEqual(r.status_code, 409)
        self.assertIn("waiting line", r.get_json()["error"])

    def test_bad_position_is_refused(self):
        bao = self.player("bao")
        hunt = self.make_hunt(bao)
        self.assertEqual(bao.post(f"/api/hunts/{hunt['id']}/arrived", json={"lat": "x"}).status_code, 400)

    # ------------------------------------------------ teammates on the map

    def walk_to(self, client, lat, lon):
        self.assertEqual(client.post("/api/me/position", json={"lat": lat, "lon": lon}).status_code, 200)

    def test_players_see_each_other_but_not_themselves(self):
        bao, lan = self.player("bao"), self.player("lan")
        hunt = self.make_hunt(bao, capacity=5)
        lan.post(f"/api/hunts/{hunt['id']}/join")
        self.walk_to(bao, 24.7950, 120.9940)
        self.walk_to(lan, 24.7960, 120.9950)
        seen_by_bao = bao.get(f"/api/hunts/{hunt['id']}/players").get_json()["players"]
        self.assertEqual([(p["name"], p["lat"], p["lon"]) for p in seen_by_bao], [("lan", 24.7960, 120.9950)])
        seen_by_lan = lan.get(f"/api/hunts/{hunt['id']}/players").get_json()["players"]
        self.assertEqual([p["name"] for p in seen_by_lan], ["bao"])

    def test_old_positions_are_hidden(self):
        bao, lan = self.player("bao"), self.player("lan")
        hunt = self.make_hunt(bao, capacity=5)
        lan.post(f"/api/hunts/{hunt['id']}/join")
        self.walk_to(lan, 24.7960, 120.9950)
        row = db.session.get(PlayerPosition, self.user_id("lan"))
        row.updated_at = datetime.now(timezone.utc) - timedelta(minutes=3)
        db.session.commit()
        self.assertEqual(bao.get(f"/api/hunts/{hunt['id']}/players").get_json()["players"], [])

    def test_waiting_line_is_neither_shown_nor_allowed(self):
        bao, lan = self.player("bao"), self.player("lan")
        hunt = self.make_hunt(bao, capacity=1)
        lan.post(f"/api/hunts/{hunt['id']}/join")  # waits in line
        self.walk_to(lan, 24.7960, 120.9950)
        self.assertEqual(lan.get(f"/api/hunts/{hunt['id']}/players").status_code, 403)
        self.assertEqual(bao.get(f"/api/hunts/{hunt['id']}/players").get_json()["players"], [])

    def test_outsiders_and_logged_out_are_refused(self):
        hunt = self.make_hunt(self.player("bao"))
        self.assertEqual(self.player("spy").get(f"/api/hunts/{hunt['id']}/players").status_code, 403)
        self.assertEqual(self.app.test_client().get(f"/api/hunts/{hunt['id']}/players").status_code, 401)

    def test_unknown_hunt(self):
        self.assertEqual(self.player("bao").get("/api/hunts/9999/game").status_code, 404)


if __name__ == "__main__":
    unittest.main()

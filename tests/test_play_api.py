"""B: the six new ways to play, through their APIs (box, wanderer, ghost, team, travelers, eyes-free)."""

import os
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

import box_code
from app import create_app
from hunt_game_api import HuntGame
from models import (BoxProof, CoinTransaction, Hunt, RacePoint, TeamLock, Traveler, TravelerMove, Treasure, User,
                    WandererCatch, db)
from wanderer import CATCH_COINS, position_at

NOW = 1_795_716_000  # a fixed moment, for the box and the wanderer


class PlayApiCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app("sqlite:///:memory:")
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.session.query(Treasure).delete()
        db.session.commit()
        self.hider = self.player("hider")
        hider_id = self.uid("hider")
        self.spots = {}
        for name, lat in (("Pond", 24.7950), ("Bell", 24.7960), ("Gate", 24.7970)):
            t = Treasure(name=name, lat=lat, lon=120.9950, created_by=hider_id)
            db.session.add(t)
            db.session.flush()
            self.spots[name] = t
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
        self.ctx.pop()

    def player(self, name):
        client = self.app.test_client()
        r = client.post("/api/register", json={"username": name, "password": "secret1"})
        self.assertEqual(r.status_code, 201, r.get_json())
        return client

    def uid(self, name):
        return db.session.execute(db.select(User.id).filter_by(username=name)).scalar_one()

    def at(self, name):
        t = self.spots[name]
        return {"lat": t.lat, "lon": t.lon}

    def coins(self, name, reason):
        return db.session.execute(db.select(db.func.coalesce(db.func.sum(CoinTransaction.amount), 0)).where(
            CoinTransaction.user_id == self.uid(name), CoinTransaction.reason == reason)).scalar_one()

    def claim(self, client, name):
        with patch("walk_proof_api.check_find", return_value=(None, [])):  # (walk proof has its own tests)
            return client.post(f"/api/treasures/{self.spots[name].id}/claim", json=self.at(name))


class BoxApiTest(PlayApiCase):
    def add_box(self):
        r = self.hider.post(f"/api/treasures/{self.spots['Pond'].id}/box")
        self.assertEqual(r.status_code, 201)
        return r.get_json()["secret"]

    def test_only_the_hider_adds_a_box_and_the_secret_shows_once(self):
        ann = self.player("ann")
        self.assertEqual(ann.post(f"/api/treasures/{self.spots['Pond'].id}/box").status_code, 403)
        secret = self.add_box()
        self.assertEqual(len(secret), 40)
        self.assertEqual(self.hider.post(f"/api/treasures/{self.spots['Pond'].id}/box").status_code, 409)
        listed = ann.get("/api/boxes").get_json()
        self.assertNotIn(secret, str(listed))
        self.assertEqual(listed["boxes"][0]["treasure"], "Pond")
        self.assertEqual(listed["can_add"], [])
        self.assertEqual({t["name"] for t in self.hider.get("/api/boxes").get_json()["can_add"]}, {"Bell", "Gate"})

    def test_a_box_blocks_the_find_until_the_code_is_typed(self):
        secret = self.add_box()
        ann = self.player("ann")
        r = self.claim(ann, "Pond")
        self.assertEqual(r.status_code, 409)
        self.assertIn("box", r.get_json()["error"])
        url = f"/api/treasures/{self.spots['Pond'].id}/box/proof"
        with patch("box_api._now", return_value=NOW):
            self.assertEqual(ann.post(url, json={"code": "000000" if box_code.code_at(secret, NOW) != "000000"
                                                 else "111111"}).status_code, 400)
            self.assertEqual(ann.post(url, json={"code": "abc"}).status_code, 400)
            ok = ann.post(url, json={"code": box_code.code_at(secret, NOW)})
        self.assertEqual(ok.status_code, 200)
        self.assertTrue(ok.get_json()["proved"])
        self.assertEqual(self.claim(ann, "Pond").status_code, 200)

    def test_each_code_works_for_one_player(self):
        secret = self.add_box()
        ann, ben = self.player("ann"), self.player("ben")
        url = f"/api/treasures/{self.spots['Pond'].id}/box/proof"
        code = box_code.code_at(secret, NOW)
        with patch("box_api._now", return_value=NOW):
            self.assertEqual(ann.post(url, json={"code": code}).status_code, 200)
            shared = ben.post(url, json={"code": code})
            self.assertEqual(shared.status_code, 409)
            self.assertIn("next one", shared.get_json()["error"])
        with patch("box_api._now", return_value=NOW + 30):
            self.assertEqual(ben.post(url, json={"code": box_code.code_at(secret, NOW + 30)}).status_code, 200)
        self.assertEqual(db.session.execute(db.select(db.func.count(BoxProof.id))).scalar_one(), 2)

    def test_removing_the_box(self):
        self.add_box()
        self.assertEqual(self.player("ann").delete(f"/api/treasures/{self.spots['Pond'].id}/box").status_code, 403)
        self.assertEqual(self.hider.delete(f"/api/treasures/{self.spots['Pond'].id}/box").status_code, 200)
        self.assertEqual(self.claim(self.player("cyd"), "Pond").status_code, 200)

    def test_logged_out_and_the_page(self):
        anon = self.app.test_client()
        self.assertEqual(anon.get("/api/boxes").status_code, 401)
        self.assertEqual(anon.get("/box").status_code, 302)
        page = self.hider.get("/box").get_data(as_text=True)
        self.assertIn("<h1>", page)
        self.assertNotIn("innerHTML", page)


class WandererApiTest(PlayApiCase):
    def seed(self):
        from wanderer_api import seed_for
        return seed_for(self.app)

    def test_footprints_never_show_where_it_is(self):
        ann = self.player("ann")
        with patch("wanderer_api._now", return_value=NOW):
            data = ann.get("/api/wanderer").get_json()
            self.assertNotIn("now", ann.get("/api/wanderer?reveal=1").get_json())  # only admins
        self.assertEqual(len(data["footprints"]), 4)
        self.assertNotIn("now", data)
        self.assertFalse(data["caught_today"])

    def test_admin_can_reveal_for_a_talk(self):
        with patch.dict(os.environ, {"ADMIN_USERS": "hider"}), patch("wanderer_api._now", return_value=NOW):
            data = self.hider.get("/api/wanderer?reveal=1").get_json()
        lat, lon = position_at(NOW, self.seed())
        self.assertAlmostEqual(data["now"]["lat"], lat, places=5)

    def test_catch_pays_once_a_day(self):
        ann = self.player("ann")
        lat, lon = position_at(NOW, self.seed())
        with patch("wanderer_api._now", return_value=NOW):
            miss = ann.post("/api/wanderer/catch", json={"lat": lat + 0.01, "lon": lon}).get_json()
            self.assertEqual(miss["result"], "cold")
            first = ann.post("/api/wanderer/catch", json={"lat": lat, "lon": lon}).get_json()
            again = ann.post("/api/wanderer/catch", json={"lat": lat, "lon": lon}).get_json()
            self.assertTrue(ann.get("/api/wanderer").get_json()["caught_today"])
        self.assertEqual(first["coins_earned"], CATCH_COINS)
        self.assertEqual(again["coins_earned"], 0)
        self.assertEqual(self.coins("ann", "wanderer_catch"), CATCH_COINS)
        self.assertEqual(db.session.execute(db.select(db.func.count(WandererCatch.id))).scalar_one(), 1)

    def test_bad_position(self):
        self.assertEqual(self.player("ann").post("/api/wanderer/catch", json={"lat": "x"}).status_code, 400)


class GhostApiTest(PlayApiCase):
    def race(self, winner, seconds, start_lat):
        hunt = Hunt(name=f"Race {winner} {seconds}", capacity=4, created_by=self.uid(winner))
        db.session.add(hunt)
        db.session.flush()
        start = datetime(2026, 11, 20, 8, 0, 0)
        db.session.add(HuntGame(hunt_id=hunt.id, treasure_id=self.spots["Pond"].id, started_at=start,
                                winner_id=self.uid(winner), finished_at=start + timedelta(seconds=seconds)))
        for s in range(0, seconds, 10):
            share = s / seconds
            db.session.add(RacePoint(hunt_id=hunt.id, user_id=self.uid(winner), at=start + timedelta(seconds=s),
                                     lat=start_lat + (24.7950 - start_lat) * share, lon=120.9950))
        db.session.commit()

    def test_the_fastest_run_is_the_ghost(self):
        ann, self.ben = self.player("ann"), self.player("ben")
        self.assertEqual(ann.get("/api/ghosts").get_json()["ghosts"], [])
        self.race("ann", 120, 24.7960)
        self.race("ben", 90, 24.7960)
        ghosts = ann.get("/api/ghosts").get_json()["ghosts"]
        self.assertEqual(ghosts, [{"treasure_id": self.spots["Pond"].id, "treasure": "Pond", "ghost": "ben",
                                   "time": "1:30", "my_best": "2:00"}])
        mine = ann.get(f"/api/ghosts/{self.spots['Pond'].id}?who=me").get_json()
        self.assertEqual((mine["ghost"], mine["duration_s"]), ("ann", 120))
        self.assertEqual(self.player("cyd").get(f"/api/ghosts/{self.spots['Pond'].id}?who=me").status_code, 404)

    def test_compare_says_who_leads_and_who_won(self):
        ann = self.player("ann")
        self.player("ben")
        self.race("ben", 100, 24.7960)
        url = f"/api/ghosts/{self.spots['Pond'].id}/compare"
        behind = ann.post(url, json={"elapsed_s": 50, "lat": 24.7960, "lon": 120.9950}).get_json()
        self.assertLess(behind["lead_m"], 0)
        self.assertIn("ben's ghost is", behind["text"])
        won = ann.post(url, json={"elapsed_s": 80, "lat": 24.7950, "lon": 120.9950}).get_json()
        self.assertTrue(won["finished"])
        self.assertIn("You beat ben's ghost by 0:20", won["text"])
        self.assertEqual(ann.post(url, json={"elapsed_s": -1, "lat": 24.79, "lon": 120.99}).status_code, 400)
        self.assertEqual(ann.post(f"/api/ghosts/{self.spots['Bell'].id}/compare",
                                  json={"elapsed_s": 1, "lat": 24.79, "lon": 120.99}).status_code, 404)


class TeamApiTest(PlayApiCase):
    def lock(self, need=2):
        r = self.hider.post(f"/api/treasures/{self.spots['Pond'].id}/team-lock", json={"need": need})
        self.assertEqual(r.status_code, 201)
        return db.session.execute(db.select(TeamLock.id)).scalar_one()

    def test_making_a_lock(self):
        url = f"/api/treasures/{self.spots['Pond'].id}/team-lock"
        self.assertEqual(self.player("ann").post(url, json={"need": 2}).status_code, 403)
        self.assertEqual(self.hider.post(url, json={"need": 5}).status_code, 400)
        self.lock()
        self.assertEqual(self.hider.post(url, json={"need": 2}).status_code, 409)

    def test_opens_only_when_two_come_together(self):
        lock_id = self.lock(2)
        ann, ben = self.player("ann"), self.player("ben")
        self.assertIn("team treasure", self.claim(ann, "Pond").get_json()["error"])
        far = ann.post(f"/api/team-locks/{lock_id}/here", json={"lat": 24.80, "lon": 120.995})
        self.assertEqual(far.status_code, 400)
        t0 = datetime(2026, 11, 20, 8, 0, 0)
        with patch("team_api._now", return_value=t0):
            first = ann.post(f"/api/team-locks/{lock_id}/here", json=self.at("Pond")).get_json()
        self.assertFalse(first["opened"])
        self.assertIn("1 of 2 here", first["text"])
        with patch("team_api._now", return_value=t0 + timedelta(seconds=90)):  # too late: ann's tap is old
            late = ben.post(f"/api/team-locks/{lock_id}/here", json=self.at("Pond")).get_json()
        self.assertFalse(late["opened"])
        with patch("team_api._now", return_value=t0 + timedelta(seconds=100)):
            together = ann.post(f"/api/team-locks/{lock_id}/here", json=self.at("Pond")).get_json()
        self.assertTrue(together["opened"])
        self.assertTrue(together["just_opened"])
        self.assertEqual(together["here"], ["ann", "ben"])
        self.assertEqual(self.coins("ann", "team_treasure"), 15)
        self.assertEqual(self.coins("ben", "team_treasure"), 15)
        self.assertEqual(self.claim(ann, "Pond").status_code, 200)
        self.assertEqual(self.claim(ben, "Pond").status_code, 200)
        with patch("team_api._now", return_value=t0 + timedelta(seconds=110)):
            ann.post(f"/api/team-locks/{lock_id}/here", json=self.at("Pond"))
        self.assertEqual(self.coins("ann", "team_treasure"), 15)  # the bonus is paid once

    def test_list(self):
        self.lock(3)
        data = self.player("ann").get("/api/team-locks").get_json()
        self.assertEqual(data["locks"][0]["need"], 3)
        self.assertEqual(data["locks"][0]["here"], [])
        self.assertEqual(data["can_add"], [])


class TravelerApiTest(PlayApiCase):
    def release(self, client, name="Golden Duck", at="Pond", goal="Gate"):
        body = {"name": name, **self.at(at)}
        if goal:
            body["goal_treasure_id"] = self.spots[goal].id
        return client.post("/api/travelers", json=body)

    def test_a_relay_to_the_goal(self):
        ann, ben, cy = self.player("ann"), self.player("ben"), self.player("cyd")
        r = self.release(ann)
        self.assertEqual(r.status_code, 201)
        duck = r.get_json()
        self.assertEqual(duck["where"], "At Pond")
        self.assertIn("Wants to reach Gate", duck["goal"])
        url = f"/api/travelers/{duck['id']}"
        self.assertEqual(ben.post(f"{url}/pick", json=self.at("Bell")).status_code, 409)  # it is not there
        picked = ben.post(f"{url}/pick", json=self.at("Pond")).get_json()
        self.assertTrue(picked["in_my_bag"])
        self.assertEqual(cy.get("/api/travelers").get_json()["travelers"][0]["where"], "In ben's bag")
        self.assertEqual(cy.post(f"{url}/pick", json=self.at("Pond")).status_code, 409)
        self.assertEqual(ben.post(f"{url}/drop", json=self.at("Pond")).status_code, 409)  # somewhere new
        ben.post(f"{url}/drop", json=self.at("Bell"))
        cy.post(f"{url}/pick", json=self.at("Bell"))
        arrived = cy.post(f"{url}/drop", json=self.at("Gate")).get_json()
        self.assertEqual(arrived["coins_earned"], 25)
        self.assertTrue(arrived["goal_reached"])
        self.assertEqual(arrived["stops"], 3)
        self.assertEqual(arrived["travelled"], "222 m")
        self.assertIn("cyd dropped it at Gate", arrived["history"][0]["text"])
        self.assertEqual(self.coins("cyd", "traveler_goal"), 25)
        ben.post(f"{url}/pick", json=self.at("Gate"))
        ben.post(f"{url}/drop", json=self.at("Bell"))
        ben.post(f"{url}/pick", json=self.at("Bell"))
        self.assertEqual(ben.post(f"{url}/drop", json=self.at("Gate")).get_json()["coins_earned"], 0)  # once only

    def test_rules_on_release_and_carrying(self):
        ann = self.player("ann")
        self.assertEqual(ann.post("/api/travelers", json={"name": "Duck", "lat": 24.70, "lon": 120.9}).status_code, 400)
        self.assertEqual(self.release(ann, goal="Pond").status_code, 400)  # goal where it starts
        for n in range(3):
            self.assertEqual(self.release(ann, name=f"Duck {n}").status_code, 201)
        self.assertEqual(self.release(ann, name="Duck 4").status_code, 409)
        ben = self.player("ben")
        ids = [t["id"] for t in ben.get("/api/travelers").get_json()["travelers"]]
        self.assertEqual(ben.post(f"/api/travelers/{ids[0]}/pick", json=self.at("Pond")).status_code, 200)
        self.assertEqual(ben.post(f"/api/travelers/{ids[1]}/pick", json=self.at("Pond")).status_code, 409)
        self.assertEqual(db.session.execute(db.select(db.func.count(TravelerMove.id))).scalar_one(), 4)
        self.assertEqual(db.session.execute(db.select(db.func.count(Traveler.id))).scalar_one(), 3)


class GuideApiTest(PlayApiCase):
    def test_guidance(self):
        ann = self.player("ann")
        pond = self.spots["Pond"].id
        far = ann.get(f"/api/guide/{pond}?lat=24.7940&lon=120.9950&heading=0").get_json()
        self.assertEqual(far["direction"], "ahead")     # the pond is north, the phone faces north
        self.assertIn("110 metres, straight ahead", far["words"])
        side = ann.get(f"/api/guide/{pond}?lat=24.7940&lon=120.9950&heading=90").get_json()
        self.assertEqual(side["direction"], "left")
        no_compass = ann.get(f"/api/guide/{pond}?lat=24.7940&lon=120.9950").get_json()
        self.assertIn("to the north", no_compass["words"])
        there = ann.get(f"/api/guide/{pond}?lat=24.7950&lon=120.9950").get_json()
        self.assertTrue(there["found"])
        self.assertEqual(ann.get(f"/api/guide/{pond}?lat=x&lon=1").status_code, 400)
        self.assertEqual(ann.get(f"/api/guide/{pond}?lat=1&lon=1&heading=400").status_code, 400)
        self.assertEqual(ann.get("/api/guide/9999?lat=1&lon=1").status_code, 404)
        self.assertEqual(self.app.test_client().get(f"/api/guide/{pond}?lat=1&lon=1").status_code, 401)


class PagesTest(PlayApiCase):
    def test_every_page_loads_and_uses_text_not_html(self):
        ann = self.player("ann")
        for path in ("/box", "/wanderer", "/ghost", "/team", "/travelers", "/eyes-free"):
            r = ann.get(path)
            self.assertEqual(r.status_code, 200, path)
            page = r.get_data(as_text=True)
            self.assertIn("<h1", page, path)
            self.assertNotIn("innerHTML", page, path)
            self.assertEqual(self.app.test_client().get(path).status_code, 302, path)

    def test_the_menu_links_them(self):
        page = self.player("ann").get("/riddles").get_data(as_text=True)
        for path in ("/box", "/wanderer", "/ghost", "/team", "/travelers", "/eyes-free"):
            self.assertIn(f'href="{path}"', page)


if __name__ == "__main__":
    unittest.main()

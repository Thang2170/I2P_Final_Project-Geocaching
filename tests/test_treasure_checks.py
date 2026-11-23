import os
import unittest
from unittest.mock import patch

from app import create_app
from models import Treasure, db
from treasure_checks import TreasureCheck, is_verified, verified_ids


class TestRule(unittest.TestCase):
    def test_demo_treasures_are_always_verified(self):
        self.assertTrue(is_verified(created_by=None, has_check=False))

    def test_player_treasures_need_a_check(self):
        self.assertFalse(is_verified(created_by=5, has_check=False))
        self.assertTrue(is_verified(created_by=5, has_check=True))


class TestVerifyApi(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"ADMIN_USERS": "admin"})
        self.env.start()
        self.app = create_app("sqlite:///:memory:")
        self.context = self.app.app_context()
        self.context.push()
        self.admin = self.player("admin")
        self.bao = self.player("bao")
        r = self.bao.post("/api/treasures", json={"name": "Troll spot", "lat": 24.80, "lon": 120.99})
        self.tid = r.get_json()["id"]

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
        self.context.pop()
        self.env.stop()

    def player(self, name):
        client = self.app.test_client()
        client.post("/api/register", json={"username": name, "password": "secret1"})
        return client

    def listed(self, client):
        return {t["name"]: t["verified"] for t in client.get("/api/treasures").get_json()}

    def test_new_treasure_shows_but_is_not_verified(self):
        self.assertEqual(self.listed(self.bao),
                         {"National Tsing Hua University": True, "Troll spot": False})

    def test_admin_verifies_and_takes_it_back(self):
        r = self.admin.post(f"/api/admin/treasures/{self.tid}/verify", json={"verified": True})
        self.assertEqual(r.get_json(), {"treasure_id": self.tid, "verified": True})
        self.assertTrue(self.listed(self.bao)["Troll spot"])
        self.admin.post(f"/api/admin/treasures/{self.tid}/verify", json={"verified": False})
        self.assertFalse(self.listed(self.bao)["Troll spot"])
        self.assertEqual(db.session.execute(db.select(TreasureCheck)).scalars().all(), [])

    def test_verifying_twice_keeps_one_check(self):
        for _ in range(2):
            self.admin.post(f"/api/admin/treasures/{self.tid}/verify", json={"verified": True})
        self.assertEqual(len(db.session.execute(db.select(TreasureCheck)).scalars().all()), 1)

    def test_players_cannot_verify(self):
        r = self.bao.post(f"/api/admin/treasures/{self.tid}/verify", json={"verified": True})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(self.app.test_client().post(f"/api/admin/treasures/{self.tid}/verify").status_code, 401)

    def test_bad_requests(self):
        self.assertEqual(self.admin.post("/api/admin/treasures/9999/verify", json={"verified": True}).status_code, 404)
        r = self.admin.post(f"/api/admin/treasures/{self.tid}/verify", json={"verified": "yes"})
        self.assertEqual(r.status_code, 400)

    def test_admin_summary_counts_unverified(self):
        data = self.admin.get("/api/admin/summary").get_json()
        self.assertEqual(data["unverified"], 1)
        self.assertEqual({t["name"]: t["verified"] for t in data["treasure_list"]},
                         {"National Tsing Hua University": True, "Troll spot": False})
        self.assertEqual(verified_ids(), {db.session.execute(db.select(Treasure.id).filter_by(created_by=None)).scalar()})


if __name__ == "__main__":
    unittest.main()

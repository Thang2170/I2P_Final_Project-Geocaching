"""The whole demo, played through the real app from a brand-new database.

If this test passes, the story we show on presentation day works:
register, hide a treasure, find it, buy a voucher, join a full hunt.
"""

import unittest

from app import create_app
from demo_content import DEMO_PASSWORD
from demo_data import seed_demo_story
from models import Treasure, db


class TestDemoStory(unittest.TestCase):
    def setUp(self):
        self.app = create_app("sqlite:///:memory:")
        self.context = self.app.app_context()
        self.context.push()
        seed_demo_story()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
        self.context.pop()

    def test_the_demo_story_works_from_a_fresh_database(self):
        # 1. a brand-new player signs up (and is logged in straight away)
        me = self.app.test_client()
        reply = me.post("/api/register", json={"username": "presenter", "password": "stage123"})
        self.assertEqual(reply.status_code, 201)
        self.assertEqual(me.get("/api/coins").get_json()["balance"], 0)

        # 2. they hide their own treasure
        reply = me.post("/api/treasures", json={"name": "My spot", "lat": 24.8, "lon": 121.0})
        self.assertEqual(reply.status_code, 201)

        # 3. they walk to one of alice's treasures and find it: +10 coins
        target = db.session.query(Treasure).filter_by(name="Pond bench").one()
        reply = me.post(f"/api/treasures/{target.id}/claim", json={"lat": target.lat, "lon": target.lon})
        self.assertEqual(reply.status_code, 200)
        self.assertEqual(reply.get_json()["balance"], 10)

        # 4. coins are not enough for a bubble tea (50), so the shop says no
        self.assertEqual(me.post("/api/shop/buy", json={"item_id": "bubble-tea"}).status_code, 402)

        # 5. the seeded demo_player has coins, so the same purchase works for them and gives a code
        player = self.app.test_client()
        reply = player.post("/api/login", json={"username": "demo_player", "password": DEMO_PASSWORD})
        self.assertEqual(reply.status_code, 200)
        reply = player.post("/api/shop/buy", json={"item_id": "bubble-tea"})
        self.assertEqual(reply.status_code, 200)
        data = reply.get_json()
        self.assertEqual(data["balance"], 10)
        self.assertRegex(data["voucher_code"], r"^TH-[A-Z0-9]{6}$")

        # 6. they join the full demo hunt and are told to wait
        hunts = player.get("/api/hunts").get_json()
        full = next(h for h in hunts if h["name"] == "Full house (demo)")
        self.assertEqual((full["playing"], full["waiting"]), (2, 0))
        reply = player.post(f"/api/hunts/{full['id']}/join")
        self.assertEqual(reply.status_code, 200)
        me_now = next(h for h in player.get("/api/hunts").get_json() if h["id"] == full["id"])["me"]
        self.assertEqual(me_now, {"state": "waiting", "position": 1})


if __name__ == "__main__":
    unittest.main()

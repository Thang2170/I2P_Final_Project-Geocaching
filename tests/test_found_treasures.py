"""A treasure you found leaves your map (it stays on everyone else's)."""

import unittest

from app import create_app
from coins import first_to_find
from models import DEMO_TREASURE, Treasure, db


class TestFirstToFind(unittest.TestCase):
    def test_the_oldest_one_you_have_not_found(self):
        self.assertEqual(first_to_find([1, 2, 3], [1]), 2)
        self.assertEqual(first_to_find([1, 2, 3], [1, 2]), 3)

    def test_nothing_found_yet(self):
        self.assertEqual(first_to_find([4, 7], []), 4)

    def test_all_found_falls_back_to_the_oldest(self):
        self.assertEqual(first_to_find([4, 7], [7, 4]), 4)

    def test_no_treasures(self):
        self.assertIsNone(first_to_find([], []))


class TestFoundTreasuresApi(unittest.TestCase):
    def setUp(self):
        self.app = create_app("sqlite:///:memory:")
        self.context = self.app.app_context()
        self.context.push()
        self.built_in = db.session.query(Treasure).filter_by(name=DEMO_TREASURE["name"]).one()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
        self.context.pop()

    def player(self, name):
        client = self.app.test_client()
        client.post("/api/register", json={"username": name, "password": "secret1"})
        return client

    def find(self, client, treasure):
        r = client.post(f"/api/treasures/{treasure.id}/claim", json={"lat": treasure.lat, "lon": treasure.lon})
        self.assertEqual(r.status_code, 200)

    def found_flags(self, client):
        return {t["name"]: t["found_by_me"] for t in client.get("/api/treasures").get_json()}

    def test_logged_out_nothing_is_marked_found(self):
        self.assertEqual(set(self.found_flags(self.app.test_client()).values()), {False})

    def test_a_found_treasure_is_marked_only_for_you(self):
        ann, bob = self.player("ann"), self.player("bob")
        self.find(ann, self.built_in)
        self.assertTrue(self.found_flags(ann)[DEMO_TREASURE["name"]])
        self.assertFalse(self.found_flags(bob)[DEMO_TREASURE["name"]])  # still on bob's map

    def test_your_own_treasure_is_not_marked_found(self):
        ann = self.player("ann")
        ann.post("/api/treasures", json={"name": "My spot", "lat": 24.8, "lon": 121.0})
        self.assertFalse(self.found_flags(ann)["My spot"])

    def test_the_map_aims_at_the_next_treasure_you_have_not_found(self):
        hider, ann = self.player("hider"), self.player("ann")
        hider.post("/api/treasures", json={"name": "Second spot", "lat": 24.8, "lon": 121.0})
        self.assertIn(DEMO_TREASURE["name"], ann.get("/").get_data(as_text=True))
        self.find(ann, self.built_in)
        html = ann.get("/").get_data(as_text=True)
        start = html.index("const treasure = ")
        self.assertIn('"Second spot"', html[start:start + 300])


class TestMapPage(unittest.TestCase):
    def setUp(self):
        self.app = create_app("sqlite:///:memory:")
        client = self.app.test_client()
        client.post("/api/register", json={"username": "ann", "password": "secret1"})
        self.html = client.get("/").get_data(as_text=True)
        self.css = client.get("/static/css/app.css").get_data(as_text=True)

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()
            db.engine.dispose()

    def test_found_treasures_are_not_drawn(self):
        self.assertIn("!t.found_by_me", self.html)

    def test_a_collected_pin_leaves_the_map(self):
        self.assertIn("collectPin(treasureId);", self.html)
        after_409 = self.html.split("if (res.status === 409)", 1)[1][:120]  # you had already found it
        self.assertIn("collectPin(treasureId);", after_409)
        self.assertIn(".pin.is-collected", self.css)


if __name__ == "__main__":
    unittest.main()

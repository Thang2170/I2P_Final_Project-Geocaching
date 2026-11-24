"""Riddle chains (riddles.py, riddle_api.py, the claim bonus, the Riddles page)."""

import unittest

from app import create_app
from models import ChainBonus, Treasure, db
from riddles import (CHAIN_BONUS, CURRENT, FOUND, LOCKED, is_complete, parse_chain, step_states)


def good(ids=(1, 2)):
    return {"title": "Campus mystery", "steps": [{"treasure_id": i, "clue": f"Riddle number {i}"} for i in ids]}


class TestRules(unittest.TestCase):
    def test_a_good_chain(self):
        self.assertEqual(parse_chain(good(), [1, 2, 3]), ("Campus mystery", [(1, "Riddle number 1"), (2, "Riddle number 2")]))

    def test_spaces_are_tidied(self):
        data = {"title": "  A   b c  ", "steps": [{"treasure_id": 1, "clue": "one\n two"}, {"treasure_id": 2, "clue": "x y z"}]}
        self.assertEqual(parse_chain(data, [1, 2]), ("A b c", [(1, "one two"), (2, "x y z")]))

    def test_bad_chains(self):
        cases = {
            "too short": good((1,)),
            "too long": good(tuple(range(1, 8))),
            "same treasure twice": good((1, 1)),
            "unknown treasure": good((1, 99)),
            "no title": {**good(), "title": ""},
            "short clue": {"title": "Fine title", "steps": [{"treasure_id": 1, "clue": "ab"}, {"treasure_id": 2, "clue": "abc"}]},
            "id as text": {"title": "Fine title", "steps": [{"treasure_id": "1", "clue": "abc"}, {"treasure_id": 2, "clue": "abc"}]},
            "not json": None,
        }
        for name, data in cases.items():
            with self.subTest(name), self.assertRaises(ValueError):
                parse_chain(data, list(range(1, 10)))

    def test_states_go_in_order(self):
        self.assertEqual(step_states([1, 2, 3], []), [CURRENT, LOCKED, LOCKED])
        self.assertEqual(step_states([1, 2, 3], [1]), [FOUND, CURRENT, LOCKED])
        self.assertEqual(step_states([1, 2, 3], [1, 3]), [FOUND, CURRENT, LOCKED])  # step 3 waits for step 2
        self.assertEqual(step_states([1, 2, 3], [3, 1, 2]), [FOUND, FOUND, FOUND])
        self.assertTrue(is_complete([1, 2], [2, 1, 9]))
        self.assertFalse(is_complete([1, 2], [2]))


class TestApi(unittest.TestCase):
    def setUp(self):
        self.app = create_app("sqlite:///:memory:")
        self.context = self.app.app_context()
        self.context.push()
        db.session.query(Treasure).delete()
        self.t = []
        for i, name in enumerate(("Bench", "Pond", "Bell"), start=1):
            t = Treasure(name=name, lat=24.79 + i * 0.001, lon=120.99)
            db.session.add(t)
            self.t.append(t)
        db.session.commit()
        self.maker, self.solver = self.player("maker"), self.player("solver")
        r = self.maker.post("/api/riddles", json=good([t.id for t in self.t]))
        self.assertEqual(r.status_code, 201)
        self.chain_id = r.get_json()["id"]

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
        self.context.pop()

    def player(self, name):
        client = self.app.test_client()
        client.post("/api/register", json={"username": name, "password": "secret1"})
        return client

    def chain(self, client):
        return next(c for c in client.get("/api/riddles").get_json()["chains"] if c["id"] == self.chain_id)

    def find(self, client, t):
        return client.post(f"/api/treasures/{t.id}/claim", json={"lat": t.lat, "lon": t.lon}).get_json()

    def test_needs_login(self):
        guest = self.app.test_client()
        self.assertEqual(guest.get("/api/riddles").status_code, 401)
        self.assertEqual(guest.post("/api/riddles", json=good()).status_code, 401)

    def test_locked_riddles_never_leave_the_server(self):
        steps = self.chain(self.solver)["steps"]
        self.assertEqual([s["state"] for s in steps], [CURRENT, LOCKED, LOCKED])
        self.assertIn("clue", steps[0])
        self.assertNotIn("clue", steps[1])
        self.assertNotIn("treasure", steps[0])  # the answer isn't given away either

    def test_finding_unlocks_the_next_riddle(self):
        self.find(self.solver, self.t[0])
        steps = self.chain(self.solver)["steps"]
        self.assertEqual([s["state"] for s in steps], [FOUND, CURRENT, LOCKED])
        self.assertEqual(steps[0]["treasure"], "Bench")
        self.assertEqual(self.chain(self.solver)["done"], 1)

    def test_finishing_pays_the_bonus_once(self):
        self.find(self.solver, self.t[0])
        self.find(self.solver, self.t[1])
        before = self.solver.get("/api/coins").get_json()["balance"]
        data = self.find(self.solver, self.t[2])
        self.assertEqual(data["chains_completed"], [{"title": "Campus mystery", "bonus": CHAIN_BONUS}])
        self.assertEqual(data["balance"], before + data["coins_earned"] + CHAIN_BONUS)
        self.assertTrue(self.chain(self.solver)["complete"])
        self.assertEqual(db.session.query(ChainBonus).count(), 1)

    def test_out_of_order_finds_count_when_you_catch_up(self):
        self.find(self.solver, self.t[2])
        self.find(self.solver, self.t[0])
        data = self.find(self.solver, self.t[1])
        self.assertEqual(len(data["chains_completed"]), 1)

    def test_normal_finds_have_no_bonus(self):
        self.assertEqual(self.find(self.solver, self.t[0])["chains_completed"], [])

    def test_bad_chain_is_refused(self):
        r = self.maker.post("/api/riddles", json=good([self.t[0].id, self.t[0].id]))
        self.assertEqual(r.status_code, 400)
        self.assertIn("already in the chain", r.get_json()["error"])

    def test_only_the_maker_deletes(self):
        self.assertEqual(self.solver.delete(f"/api/riddles/{self.chain_id}").status_code, 403)
        self.assertEqual(self.maker.delete(f"/api/riddles/{self.chain_id}").status_code, 200)
        self.assertEqual(self.solver.get("/api/riddles").get_json()["chains"], [])
        self.assertEqual(self.maker.delete("/api/riddles/999").status_code, 404)

    def test_pages(self):
        html = self.solver.get("/riddles").get_data(as_text=True)
        self.assertIn('fetch("/api/riddles"', html)
        self.assertNotIn(".innerHTML", html)
        self.assertIn('href="/riddles"', html)  # the top bar link
        map_html = self.solver.get("/").get_data(as_text=True)
        self.assertIn("data.chains_completed", map_html)


if __name__ == "__main__":
    unittest.main()

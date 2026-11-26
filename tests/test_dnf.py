"""B: "I couldn't find it" reports (dnf.py, dnf_api.py)."""

import unittest
from datetime import datetime, timedelta, timezone

from app import create_app
from dnf import (ALREADY, MISSING_AFTER, OWN, REPORT_RADIUS_M, TOO_FAR, board_text, is_missing,
                 just_went_missing, open_reporters, owner_text, problem_text, report_problem, thanks_text)
from location import FOUND_RADIUS_M
from models import CoinTransaction, MissingAlert, Notification, Treasure, User, db

SPOT = (24.7900, 120.9900)
NEAR = {"lat": 24.79003, "lon": 120.99003}   # about 4 m away
FAR = {"lat": 24.7920, "lon": 120.9900}      # about 220 m away


class DnfRulesTest(unittest.TestCase):
    def test_report_problems(self):
        self.assertEqual(report_problem(True, 0, False), OWN)
        self.assertEqual(report_problem(False, REPORT_RADIUS_M + 1, False), TOO_FAR)
        self.assertEqual(report_problem(False, 5, True), ALREADY)
        self.assertIsNone(report_problem(False, REPORT_RADIUS_M, False))

    def test_you_can_report_from_further_than_you_can_find(self):
        self.assertGreater(REPORT_RADIUS_M, FOUND_RADIUS_M)

    def test_problem_text(self):
        self.assertIn("221 m away", problem_text(TOO_FAR, 220.6))
        self.assertIn("your own", problem_text(OWN))
        self.assertIn("already", problem_text(ALREADY))
        with self.assertRaises(ValueError):
            problem_text("nope")

    def test_only_reports_after_the_last_find_count(self):
        t0 = datetime(2026, 11, 1, 12)
        reports = [(1, t0), (2, t0 + timedelta(hours=2)), (2, t0 + timedelta(hours=3)), (3, t0 + timedelta(hours=4))]
        self.assertEqual(open_reporters(reports, None), {1, 2, 3})
        self.assertEqual(open_reporters(reports, t0 + timedelta(hours=1)), {2, 3})
        self.assertEqual(open_reporters(reports, t0 + timedelta(hours=5)), set())

    def test_missing_after_three_and_told_once(self):
        self.assertFalse(is_missing(MISSING_AFTER - 1))
        self.assertTrue(is_missing(MISSING_AFTER))
        self.assertTrue(just_went_missing(MISSING_AFTER - 1, MISSING_AFTER))
        self.assertFalse(just_went_missing(MISSING_AFTER, MISSING_AFTER + 1))

    def test_texts(self):
        self.assertEqual(board_text(0), "")
        self.assertIn("1 player couldn't", board_text(1))
        self.assertIn("Maybe missing", board_text(3))
        self.assertIn("2 more players", thanks_text(1))
        self.assertIn("1 more player and", thanks_text(2))
        self.assertIn("marked maybe missing", thanks_text(3))
        self.assertIn('"Pond"', owner_text("Pond", 3))


class DnfApiTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app("sqlite:///:memory:")
        self.ctx = self.app.app_context()
        self.ctx.push()
        self.owner = self.client("olga")
        res = self.owner.post("/api/treasures", json={"name": "Rock", "lat": SPOT[0], "lon": SPOT[1]})
        self.tid = res.get_json()["id"]

    def tearDown(self):
        db.session.remove()
        self.ctx.pop()

    def client(self, name):
        c = self.app.test_client()
        c.post("/api/register", json={"username": name, "password": "secret1"})
        return c

    def report(self, client, where=NEAR):
        return client.post(f"/api/treasures/{self.tid}/not-found", json=where)

    def board(self, client):
        return next(t for t in client.get("/api/treasures").get_json() if t["id"] == self.tid)["not_found"]

    def test_needs_login_a_real_treasure_and_a_position(self):
        self.assertEqual(self.app.test_client().post(f"/api/treasures/{self.tid}/not-found", json=NEAR).status_code, 401)
        ann = self.client("ann")
        self.assertEqual(ann.post("/api/treasures/999/not-found", json=NEAR).status_code, 404)
        self.assertEqual(ann.post(f"/api/treasures/{self.tid}/not-found", json={"lat": "x"}).status_code, 400)

    def test_refusals(self):
        self.assertEqual(self.report(self.owner).get_json()["problem"], OWN)
        ann = self.client("ann")
        res = self.report(ann, FAR)
        self.assertEqual(res.status_code, 400)
        self.assertIn("Walk to the spot", res.get_json()["error"])
        self.assertEqual(self.report(ann).status_code, 201)
        res = self.report(ann)
        self.assertEqual(res.status_code, 409)
        self.assertEqual(self.board(ann)["count"], 1)  # one player, counted once

    def test_three_players_mark_it_missing_and_the_owner_is_told_once(self):
        for i, name in enumerate(("ann", "bob", "cat"), start=1):
            data = self.report(self.client(name)).get_json()
            self.assertEqual(data["count"], i)
        self.assertTrue(data["missing"])
        self.assertIn("its owner has been told", data["thanks"])
        self.assertTrue(self.board(self.owner)["missing"])
        self.report(self.client("dan"))
        self.assertEqual(db.session.query(MissingAlert).count(), 1)
        bell = self.owner.get("/api/notifications").get_json()
        items = [n for n in bell["items"] if n["kind"] == "treasure_missing"]
        self.assertEqual(len(items), 1)
        self.assertIn('"Rock"', items[0]["text"])
        self.assertEqual(items[0]["link"], f"/?treasure={self.tid}")

    def test_a_find_clears_the_reports(self):
        for name in ("ann", "bob", "cat"):
            self.report(self.client(name))
        finder = db.session.execute(db.select(User).filter_by(username="ann")).scalar_one()
        db.session.add(CoinTransaction(user_id=finder.id, amount=10, reason="found_treasure", treasure_id=self.tid,
                                       created_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(seconds=5)))
        db.session.commit()
        self.assertEqual(self.board(self.owner), {"count": 0, "missing": False, "text": ""})

    def test_a_treasure_without_owner_is_marked_but_nobody_is_told(self):
        built_in = db.session.execute(db.select(Treasure).filter_by(created_by=None)).scalars().first()
        self.tid = built_in.id
        here = {"lat": built_in.lat, "lon": built_in.lon}
        for name in ("ann", "bob", "cat"):
            self.report(self.client(name), here)
        self.assertEqual(db.session.query(Notification).filter_by(kind="treasure_missing").count(), 0)
        self.assertIsNone(db.session.query(MissingAlert).one().notification_id)


if __name__ == "__main__":
    unittest.main()

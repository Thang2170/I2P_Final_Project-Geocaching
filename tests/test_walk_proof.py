"""Prove you walked: the GPS trail before a find (walk_proof.py, walk_proof_api.py, admin page)."""

import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from app import create_app
from models import CoinTransaction, FindCheck, Treasure, User, WalkPoint, db
from walk_proof import (BLOCK, FLAG, MAX_POINTS_KEPT, NO_WALK, TELEPORT, describe, parse_mode,
                        recent, suspicious_reasons, teleports, walked_there)
from walk_proof_api import record_point

NOW = datetime(2026, 11, 24, 12, 0, tzinfo=timezone.utc)
TREASURE = (24.795324, 120.994796)
D = 0.001  # about 111 m of latitude


def ago(seconds):
    return NOW - timedelta(seconds=seconds)


def walk_in(from_m=200, minutes=3):
    """A believable walk: points every 10 s from about from_m south of the treasure up to it."""
    steps = minutes * 6
    return [(ago(10 * (steps - i)), TREASURE[0] - (from_m / 111_000) * (1 - i / steps), TREASURE[1])
            for i in range(steps)]


class TestRules(unittest.TestCase):
    def test_mode(self):
        self.assertEqual(parse_mode(None), FLAG)
        self.assertEqual(parse_mode(" Block "), BLOCK)
        with self.assertRaises(ValueError):
            parse_mode("maybe")

    def test_a_real_walk_is_fine(self):
        self.assertEqual(suspicious_reasons(walk_in(), TREASURE, TREASURE, NOW), [])

    def test_appearing_at_the_treasure(self):
        self.assertEqual(suspicious_reasons([], TREASURE, TREASURE, NOW), [NO_WALK])
        standing = [(ago(60), *TREASURE), (ago(30), *TREASURE)]
        self.assertEqual(suspicious_reasons(standing, TREASURE, TREASURE, NOW), [NO_WALK])

    def test_teleporting(self):
        # 2 km away a few seconds ago, now at the treasure
        trail = [(ago(5), TREASURE[0] - 18 * D, TREASURE[1])]
        self.assertEqual(suspicious_reasons(trail, TREASURE, TREASURE, NOW), [TELEPORT])

    def test_gps_wobble_is_not_a_teleport(self):
        wobble = [(ago(2), TREASURE[0] + 0.0006, TREASURE[1]), (ago(1), TREASURE[0], TREASURE[1])]  # 67 m in 1 s
        self.assertEqual(teleports(wobble), [])

    def test_a_long_bus_ride_ago_does_not_count(self):
        old = [(ago(3600), TREASURE[0] - 50 * D, TREASURE[1])]  # an hour ago, far away
        self.assertEqual(recent(old, NOW), [])
        self.assertEqual(suspicious_reasons(old + walk_in(), TREASURE, TREASURE, NOW), [])

    def test_walked_there(self):
        self.assertTrue(walked_there([(NOW, TREASURE[0] - D, TREASURE[1])], TREASURE))
        self.assertFalse(walked_there([(NOW, *TREASURE)], TREASURE))

    def test_words(self):
        self.assertIn("faster than anyone can run", describe([TELEPORT]))
        self.assertIn("without walking there", describe([TELEPORT, NO_WALK]))


class Base(unittest.TestCase):
    mode = None

    def setUp(self):
        env = {"STEPQUEST_WALK_PROOF": self.mode} if self.mode else {}
        patcher = patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)
        if not self.mode:
            os.environ.pop("STEPQUEST_WALK_PROOF", None)
        self.app = create_app("sqlite:///:memory:")
        self.context = self.app.app_context()
        self.context.push()
        self.player = self.app.test_client()
        self.player.post("/api/register", json={"username": "ann", "password": "secret1"})
        self.ann = db.session.execute(db.select(User).filter_by(username="ann")).scalar_one()
        self.treasure = db.session.execute(db.select(Treasure)).scalars().first()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
        self.context.pop()

    def walk_up(self):
        """Old points from a believable walk, saved as if the map had sent them."""
        for when, lat, lon in walk_in():
            record_point(self.ann.id, lat, lon, when=datetime.now(timezone.utc) - (NOW - when))
        db.session.commit()

    def claim(self):
        t = self.treasure
        return self.player.post(f"/api/treasures/{t.id}/claim", json={"lat": t.lat, "lon": t.lon})


class TestFlagMode(Base):
    def test_the_map_builds_your_trail(self):
        self.player.post("/api/me/position", json={"lat": 24.79, "lon": 120.99})
        self.assertEqual(db.session.query(WalkPoint).filter_by(user_id=self.ann.id).count(), 1)

    def test_a_real_walk_is_paid_and_not_flagged(self):
        self.walk_up()
        self.assertEqual(self.claim().status_code, 200)
        self.assertEqual(db.session.query(FindCheck).count(), 0)

    def test_a_faked_find_is_paid_but_flagged(self):
        self.assertEqual(self.claim().status_code, 200)  # flag mode: still paid
        check = db.session.execute(db.select(FindCheck)).scalar_one()
        self.assertEqual((check.user_id, check.treasure_id, check.reasons), (self.ann.id, self.treasure.id, NO_WALK))

    def test_old_points_are_forgotten(self):
        record_point(self.ann.id, 24.7, 120.9, when=datetime.now(timezone.utc) - timedelta(hours=2))
        record_point(self.ann.id, 24.7, 120.9)
        db.session.commit()
        self.assertEqual(db.session.query(WalkPoint).count(), 1)

    def test_never_too_many_points(self):
        start = datetime.now(timezone.utc) - timedelta(minutes=10)
        for i in range(MAX_POINTS_KEPT + 20):
            record_point(self.ann.id, 24.7, 120.9, when=start + timedelta(seconds=i))
        db.session.commit()
        self.assertEqual(db.session.query(WalkPoint).count(), MAX_POINTS_KEPT)


class TestBlockMode(Base):
    mode = "block"

    def test_a_faked_find_is_refused(self):
        r = self.claim()
        self.assertEqual(r.status_code, 403)
        self.assertIn("couldn't see you walk here", r.get_json()["error"])
        self.assertEqual(db.session.query(CoinTransaction).filter_by(user_id=self.ann.id).count(), 0)

    def test_a_real_walk_is_paid(self):
        self.walk_up()
        self.assertEqual(self.claim().status_code, 200)


class TestAdminReview(Base):
    def setUp(self):
        super().setUp()
        self.claim()  # a flagged find
        self.admin = self.app.test_client()
        self.admin.post("/api/register", json={"username": "admin", "password": "secret1"})
        self.check_id = db.session.execute(db.select(FindCheck.id)).scalar_one()

    def balance(self):
        return self.player.get("/api/coins").get_json()["balance"]

    def test_only_admins(self):
        self.assertEqual(self.player.get("/api/admin/suspicious-finds").status_code, 403)
        self.assertEqual(self.player.post(f"/api/admin/suspicious-finds/{self.check_id}",
                                          json={"action": "keep"}).status_code, 403)

    def test_the_list(self):
        finds = self.admin.get("/api/admin/suspicious-finds").get_json()["finds"]
        self.assertEqual([(f["player"], f["treasure"]) for f in finds], [("ann", self.treasure.name)])
        self.assertIn("without walking there", finds[0]["why"])

    def test_keep(self):
        before = self.balance()
        r = self.admin.post(f"/api/admin/suspicious-finds/{self.check_id}", json={"action": "keep"})
        self.assertEqual(r.get_json()["decision"], "kept")
        self.assertEqual(self.balance(), before)
        self.assertEqual(self.admin.get("/api/admin/suspicious-finds").get_json()["finds"], [])

    def test_reverse_takes_the_coins_back(self):
        before = self.balance()
        r = self.admin.post(f"/api/admin/suspicious-finds/{self.check_id}", json={"action": "reverse"})
        self.assertEqual(r.get_json()["decision"], "reversed")
        self.assertEqual(self.balance(), before - 10)
        self.walk_up()
        self.assertEqual(self.claim().status_code, 200)  # they can still find it for real

    def test_bad_requests(self):
        url = f"/api/admin/suspicious-finds/{self.check_id}"
        self.assertEqual(self.admin.post(url, json={"action": "delete"}).status_code, 400)
        self.assertEqual(self.admin.post("/api/admin/suspicious-finds/999", json={"action": "keep"}).status_code, 404)
        self.admin.post(url, json={"action": "keep"})
        self.assertEqual(self.admin.post(url, json={"action": "reverse"}).status_code, 409)

    def test_admin_page_has_the_list(self):
        html = self.admin.get("/admin").get_data(as_text=True)
        self.assertIn('id="suspects"', html)
        self.assertIn("/api/admin/suspicious-finds", html)
        self.assertNotIn(".innerHTML", html.split("B: suspicious finds", 1)[1].split("function setText", 1)[0])


if __name__ == "__main__":
    unittest.main()

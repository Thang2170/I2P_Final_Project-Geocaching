import os
import unittest
from unittest.mock import patch

from admin_api import admin_names
from app import create_app
from coin_api import FOUND_REASON
from models import CoinTransaction, Treasure, User, db


class TestAdminApi(unittest.TestCase):
    def setUp(self):
        # The real app (every blueprint, the demo treasure and hunt), on a throwaway database
        self.app = create_app("sqlite:///:memory:")
        self.context = self.app.app_context()
        self.context.push()
        self.admin = self.app.test_client()
        self.admin.post("/api/register", json={"username": "admin", "password": "secret1"})
        self.player = self.app.test_client()
        self.player.post("/api/register", json={"username": "bao", "password": "secret1"})

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
        self.context.pop()

    def test_default_admin_name(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(admin_names(), {"admin"})

    def test_admin_names_come_from_the_environment(self):
        with patch.dict(os.environ, {"ADMIN_USERS": " alice, bao ,"}):
            self.assertEqual(admin_names(), {"alice", "bao"})

    def test_logged_out_is_sent_to_login(self):
        r = self.app.test_client().get("/admin")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login", r.headers["Location"])
        self.assertEqual(self.app.test_client().get("/api/admin/summary").status_code, 401)

    def test_other_players_are_refused(self):
        r = self.player.get("/admin")
        self.assertEqual(r.status_code, 403)
        self.assertIn("Admins only", r.get_data(as_text=True))
        self.assertEqual(self.player.get("/api/admin/summary").status_code, 403)

    def test_a_name_from_the_environment_is_let_in(self):
        with patch.dict(os.environ, {"ADMIN_USERS": "bao"}):
            self.assertEqual(self.player.get("/api/admin/summary").status_code, 200)
            self.assertEqual(self.admin.get("/api/admin/summary").status_code, 403)

    def test_admin_page_loads_with_the_live_board(self):
        html = self.admin.get("/admin").get_data(as_text=True)
        self.assertIn('id="feed"', html)
        self.assertIn("css/app.css", html)

    def test_summary_counts_what_is_in_the_database(self):
        data = self.admin.get("/api/admin/summary").get_json()
        self.assertEqual((data["players"], data["treasures"], data["finds"], data["coins_paid"], data["hunts"]),
                         (2, 1, 0, 0, 1))
        self.assertEqual(data["treasure_list"][0]["creator"], "demo")
        self.assertIsNone(data["treasure_list"][0]["photo_url"])

    def test_events_show_the_latest_actions_newest_first(self):
        bao = db.session.execute(db.select(User).filter_by(username="bao")).scalar_one()
        demo = db.session.execute(db.select(Treasure)).scalars().first()
        self.player.post("/api/treasures", json={"name": "Pond", "lat": 24.80, "lon": 120.99})
        db.session.add(CoinTransaction(user_id=bao.id, amount=10, reason=FOUND_REASON, treasure_id=demo.id))
        db.session.commit()

        data = self.admin.get("/api/admin/summary").get_json()
        self.assertEqual((data["finds"], data["coins_paid"], data["treasures"]), (1, 10, 2))
        whats = [e["what"] for e in data["events"]]
        self.assertIn('found "National Tsing Hua University" (+10 coins)', whats)
        self.assertIn('hid "Pond"', whats)
        self.assertEqual(whats.count("joined the club"), 2)
        whens = [e["when"] for e in data["events"]]
        self.assertEqual(whens, sorted(whens, reverse=True))
        self.assertTrue(whens[0].endswith("+00:00"))  # times are marked as UTC for the browser


if __name__ == "__main__":
    unittest.main()

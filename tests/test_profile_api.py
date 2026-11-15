import unittest

from app import create_app
from models import DEMO_TREASURE, Treasure, db


class ProfileTestCase(unittest.TestCase):
    def setUp(self):
        # A throwaway in-memory database, so tests never touch geohunt.db.
        self.app = create_app("sqlite:///:memory:")
        self.context = self.app.app_context()
        self.context.push()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
        self.context.pop()

    def player(self, name):
        client = self.app.test_client()
        client.post("/api/register", json={"username": name, "password": "secret1"})
        return client


class TestProfileApi(ProfileTestCase):
    def test_needs_a_login(self):
        self.player("ann")
        self.assertEqual(self.app.test_client().get("/api/players/ann").status_code, 401)

    def test_unknown_or_impossible_names(self):
        ann = self.player("ann")
        for name in ("nobody", "ab", "a%20b"):
            with self.subTest(name=name):
                self.assertEqual(ann.get(f"/api/players/{name}").status_code, 404)

    def test_a_new_players_profile(self):
        ann = self.player("ann")
        data = self.player("bob").get("/api/players/ann").get_json()
        self.assertEqual((data["username"], data["is_me"], data["avatar"]["letter"]), ("ann", False, "A"))
        self.assertTrue(data["joined"].startswith("Joined "))
        self.assertEqual(data["stats"]["coins"], 0)
        self.assertEqual((data["stats"]["hunts"], data["recent_hunts"], data["recent_posts"]), (0, [], []))
        self.assertTrue(ann.get("/api/players/ann").get_json()["is_me"])

    def test_shows_what_the_player_did(self):
        ann = self.player("ann")
        ann.post("/api/treasures", json={"name": "Bike rack", "lat": 24.8, "lon": 121.0})
        ann.post("/api/posts", json={"text": "Hello everyone"})
        built_in = db.session.query(Treasure).filter_by(name=DEMO_TREASURE["name"]).one()
        ann.post(f"/api/treasures/{built_in.id}/claim", json={"lat": built_in.lat, "lon": built_in.lon})
        ann.post("/api/journeys", json={"treasure_id": built_in.id, "distance_m": 750, "duration_s": 600,
                                        "lat": built_in.lat, "lon": built_in.lon})
        data = self.player("bob").get("/api/players/ann").get_json()
        stats = data["stats"]
        self.assertEqual((stats["coins"], stats["found"], stats["hidden"]), (10, 1, 1))
        self.assertEqual((stats["hunts"], stats["distance_km"], stats["rank"], stats["players"]), (1, 0.75, 1, 2))
        self.assertEqual(data["hidden_treasures"], ["Bike rack"])
        self.assertEqual([p["text"] for p in data["recent_posts"]], ["Hello everyone"])
        self.assertEqual(data["recent_hunts"][0]["treasure"], DEMO_TREASURE["name"])

    def test_hunt_posts_are_not_listed_as_written_posts(self):
        ann = self.player("ann")
        built_in = db.session.query(Treasure).filter_by(name=DEMO_TREASURE["name"]).one()
        ann.post("/api/journeys", json={"treasure_id": built_in.id, "distance_m": 750, "duration_s": 600,
                                        "lat": built_in.lat, "lon": built_in.lon})
        ann.get("/api/feed")  # makes the automatic hunt post
        self.assertEqual(ann.get("/api/players/ann").get_json()["recent_posts"], [])

    def test_no_private_details(self):
        data = self.player("bob").get("/api/players/bob").get_json()
        text = str(data)
        for secret in ("password", "weight", "hash"):
            with self.subTest(secret=secret):
                self.assertNotIn(secret, text)


class TestProfileLinks(ProfileTestCase):
    def test_the_profile_page_loads(self):
        html = self.app.test_client().get("/players/ann").get_data(as_text=True)
        self.assertIn("/api/players/", html)
        self.assertNotIn(".innerHTML", html)

    def test_the_your_account_button_can_really_be_hidden(self):
        # It is only for your own profile; a plain-link rule must not override [hidden] on it.
        css = self.app.test_client().get("/static/css/app.css").get_data(as_text=True)
        self.assertIn(".profile__edit[hidden] { display: none; }", css)
        self.assertIn(".profile .panel > a:not(.btn)", css)

    def test_chat_avatars_and_names_link_to_profiles(self):
        ann = self.player("ann")
        hid = ann.post("/api/hunts", json={"name": "Walk"}).get_json()["id"]
        html = ann.get(f"/hunts/{hid}/chat").get_data(as_text=True)
        self.assertIn("/players/${encodeURIComponent(username)}", html)
        self.assertIn("playerLink(p.username, avatarEl(p.avatar)", html)   # the member strip
        self.assertIn("playerLink(m.author, avatarEl(m.avatar))", html)     # message avatars

    def test_community_avatars_and_names_link_to_profiles(self):
        html = self.app.test_client().get("/community").get_data(as_text=True)
        for part in ("playerLink(p.author, avatarEl(p.avatar))", "playerLink(c.author, avatarEl(c.avatar))",
                     "playerLink(p.username", 'id="meLink"'):
            with self.subTest(part=part):
                self.assertIn(part, html)

    def test_leaderboard_names_link_to_profiles(self):
        html = self.app.test_client().get("/leaderboard").get_data(as_text=True)
        self.assertIn("/players/${encodeURIComponent(p.username)}", html)


if __name__ == "__main__":
    unittest.main()

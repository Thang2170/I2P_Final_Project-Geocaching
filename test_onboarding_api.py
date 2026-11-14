import unittest
from unittest.mock import patch

from app import create_app
from models import DEMO_TREASURE, Hunt, Treasure, TourSeen, db
from onboarding import TOUR_STEPS


class TestOnboardingApi(unittest.TestCase):
    def setUp(self):
        self.app = create_app("sqlite:///:memory:")
        self.context = self.app.app_context()
        self.context.push()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
        self.context.pop()

    def player(self, name="newbie"):
        client = self.app.test_client()
        client.post("/api/register", json={"username": name, "password": "secret1"})
        return client

    def quests(self, client):
        items = client.get("/api/onboarding").get_json()["quests"]["items"]
        return {q["id"]: q["done"] for q in items}

    def test_needs_a_login(self):
        guest = self.app.test_client()
        self.assertEqual(guest.get("/api/onboarding").status_code, 401)
        self.assertEqual(guest.post("/api/onboarding/seen", json={"how": "skipped"}).status_code, 401)

    def test_a_new_player_gets_the_tour(self):
        data = self.player().get("/api/onboarding").get_json()
        self.assertTrue(data["show"])
        self.assertEqual(data["username"], "newbie")
        self.assertEqual([s["id"] for s in data["steps"]], [s["id"] for s in TOUR_STEPS])
        self.assertEqual(data["quests"]["done"], 0)

    def test_finishing_or_skipping_stops_it_popping_up(self):
        for how in ("finished", "skipped"):
            with self.subTest(how=how):
                client = self.player(f"p_{how}")
                r = client.post("/api/onboarding/seen", json={"how": how})
                self.assertEqual(r.status_code, 200)
                self.assertFalse(client.get("/api/onboarding").get_json()["show"])

    def test_replay_shows_it_again(self):
        client = self.player()
        client.post("/api/onboarding/seen", json={"how": "skipped"})
        self.assertTrue(client.get("/api/onboarding?again=1").get_json()["show"])

    def test_seeing_it_twice_keeps_one_row(self):
        client = self.player()
        client.post("/api/onboarding/seen", json={"how": "skipped"})
        client.post("/api/onboarding/seen", json={"how": "finished"})
        rows = db.session.query(TourSeen).all()
        self.assertEqual([(r.how) for r in rows], ["finished"])

    def test_bad_ending_is_refused(self):
        client = self.player()
        self.assertEqual(client.post("/api/onboarding/seen", json={"how": "later"}).status_code, 400)
        self.assertEqual(db.session.query(TourSeen).count(), 0)

    def test_one_player_seeing_it_does_not_hide_it_for_others(self):
        self.player("first").post("/api/onboarding/seen", json={"how": "finished"})
        self.assertTrue(self.player("second").get("/api/onboarding").get_json()["show"])

    def test_quests_tick_themselves_off(self):
        client = self.player()
        client.post("/api/me/weight", json={"weight_kg": 60})
        client.post("/api/treasures", json={"name": "My spot", "lat": 24.8, "lon": 121.0})
        client.post("/api/posts", json={"text": "Hi everyone!"})
        hunt = db.session.query(Hunt).first()
        client.post(f"/api/hunts/{hunt.id}/join")
        built_in = db.session.query(Treasure).filter_by(name=DEMO_TREASURE["name"]).one()
        client.post(f"/api/treasures/{built_in.id}/claim", json={"lat": built_in.lat, "lon": built_in.lon})
        done = self.quests(client)
        self.assertEqual(done, {"weight": True, "find": True, "hide": True, "post": True,
                                "join": True, "buy": False})

    def test_quests_are_per_player(self):
        busy = self.player("busy")
        busy.post("/api/posts", json={"text": "Hi"})
        self.assertFalse(self.quests(self.player("quiet"))["post"])


class TestTourOnPages(unittest.TestCase):
    def setUp(self):
        self.app = create_app("sqlite:///:memory:")
        self.client = self.app.test_client()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()
            db.engine.dispose()

    def test_the_map_page_has_the_tour(self):
        with patch("app.current_user", return_value=object()):  # "/" needs a login
            html = self.client.get("/").get_data(as_text=True)
        for part in ('id="tour"', 'id="tourNext"', 'id="tourSkip"', "/api/onboarding", "/api/onboarding/seen"):
            with self.subTest(part=part):
                self.assertIn(part, html)

    def test_the_map_has_a_quests_button_that_reopens_the_board(self):
        with patch("app.current_user", return_value=object()):
            html = self.client.get("/").get_data(as_text=True)
        self.assertIn('id="questBtn"', html)
        self.assertIn("open(steps.length - 1)", html)       # opens at the quest board
        self.assertIn('"/api/onboarding" + (again ? "?again=1" : "")', html)  # fresh progress

    def test_the_tour_never_uses_innerhtml(self):
        tour = open("templates/_tour.html", encoding="utf-8").read()
        self.assertNotIn(".innerHTML", tour)

    def test_account_page_can_replay_it(self):
        self.assertIn('href="/?tour"', self.client.get("/login").get_data(as_text=True))

    def test_css_styles_the_tour(self):
        css = self.client.get("/static/css/app.css").get_data(as_text=True)
        self.assertIn(".tour__box", css)
        self.assertIn(".quest-btn", css)


if __name__ == "__main__":
    unittest.main()

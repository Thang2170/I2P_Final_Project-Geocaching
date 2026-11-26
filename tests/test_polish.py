"""B: the polish round: hunt status lines, races on profiles, the leaderboard without empty rows,
the welcome lists without repeats, StepQuest error pages and consistent demo data."""

import unittest
from datetime import datetime, timedelta

from app import create_app
from demo_data import seed_demo_story
from leaderboard import on_the_board
from models import Hunt, HuntMember, Treasure, TreasureCondition, User, db
from player_profile import race_result
from queue_logic import PLAYING, WAITING, status_text
from ratings import HOME_TOP, HOME_TRENDING, home_lists


class RulesTest(unittest.TestCase):
    def test_status_text(self):
        self.assertEqual(status_text({"state": PLAYING, "position": 2}), "You are playing (#2)")
        self.assertEqual(status_text({"state": WAITING, "position": 1}), "You are waiting: #1 in line")
        self.assertEqual(status_text({"state": PLAYING, "position": 3}, finished=True), "You raced in this hunt")
        self.assertEqual(status_text({"state": WAITING, "position": 1}, finished=True), "You were in line for this race")

    def test_race_result(self):
        self.assertEqual(race_result("ben", "ben", True), "You won")
        self.assertEqual(race_result("ben", "ben", False), "Won it")
        self.assertEqual(race_result("ben", "amy", False), "ben won")
        self.assertEqual(race_result(None, "amy", True), "Nobody won")

    def test_on_the_board(self):
        rows = [{"username": "a", "coins": 0, "found": 0, "hidden": 0},
                {"username": "b", "coins": 5, "found": 0, "hidden": 0},
                {"username": "c", "coins": 0, "found": 0, "hidden": 2}]
        self.assertEqual([r["username"] for r in on_the_board(rows)], ["b", "c"])

    def test_home_lists_have_no_repeats(self):
        top, hot = home_lists([1, 2], [3, 2, 4, 5, 6], [2, 7, 1, 8, 9, 10])
        self.assertEqual(top, [1, 2, 3, 4][:HOME_TOP])
        self.assertEqual(hot, [7, 8, 9][:HOME_TRENDING])
        self.assertFalse(set(top) & set(hot))


class PagesTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app("sqlite:///:memory:")
        self.ctx = self.app.app_context()
        self.ctx.push()

    def tearDown(self):
        db.session.remove()
        self.ctx.pop()

    def client(self, name):
        c = self.app.test_client()
        c.post("/api/register", json={"username": name, "password": "secret1"})
        return c

    def test_error_pages(self):
        c = self.client("ann")
        res = c.get("/no-such-page")
        self.assertEqual(res.status_code, 404)
        html = res.get_data(as_text=True)
        self.assertIn("Nothing here", html)
        self.assertIn('id="menuButton"', html)  # the normal top bar, so you can find your way back
        self.assertEqual(c.get("/api/no-such-thing").get_json(), {"error": "Not found"})
        wrong = c.delete("/api/leaderboard")
        self.assertEqual(wrong.status_code, 405)
        self.assertIn("error", wrong.get_json())

    def test_finished_race_card_and_profile(self):
        ann, bob = self.client("ann"), self.client("bob")
        self.client("cat")
        from hunt_game_api import HuntGame
        hunt = Hunt(name="Race", capacity=2)
        db.session.add(hunt)
        db.session.flush()
        ids = {u.username: u.id for u in db.session.query(User)}
        for name in ("ann", "bob"):
            db.session.add(HuntMember(hunt_id=hunt.id, user_id=ids[name]))
        treasure = db.session.query(Treasure).first()
        db.session.add(HuntGame(hunt_id=hunt.id, treasure_id=treasure.id, started_at=datetime.utcnow() - timedelta(minutes=5),
                                winner_id=ids["bob"], finished_at=datetime.utcnow()))
        db.session.commit()
        card = next(h for h in ann.get("/api/hunts").get_json() if h["id"] == hunt.id)
        self.assertEqual(card["me"]["text"], "You raced in this hunt")
        mine = ann.get("/api/players/ann").get_json()["races"]
        self.assertEqual(mine, [{"name": "Race", "result": "bob won", "ago": mine[0]["ago"],
                                 "replay": f"/hunts/{hunt.id}/replay"}])
        self.assertEqual(bob.get("/api/players/bob").get_json()["races"][0]["result"], "You won")
        cat = self.app.test_client()
        cat.post("/api/login", json={"username": "cat", "password": "secret1"})
        seen_by_cat = cat.get("/api/players/bob").get_json()["races"][0]
        self.assertEqual(seen_by_cat["result"], "Won it")
        self.assertIsNone(seen_by_cat["replay"])  # cat wasn't in the race: no replay link

    def test_leaderboard_leaves_out_empty_players(self):
        ann = self.client("ann")
        self.client("bob")
        names = [r["username"] for r in ann.get("/api/leaderboard").get_json()]
        self.assertNotIn("bob", names)
        self.assertNotIn("ann", names)

    def test_rankings_hide_rain_treasures_that_are_not_out(self):
        owner, ann = self.client("olga"), self.client("ann")
        tid = owner.post("/api/treasures", json={"name": "Puddle", "lat": 24.7901, "lon": 120.9901,
                                                 "appears": "rain"}).get_json()["id"]
        self.assertIsNotNone(db.session.get(TreasureCondition, tid))
        seen = ann.get("/api/treasures/rankings").get_json()
        listed = {t["name"] for part in ("top_rated", "trending", "new") for t in seen[part]}
        listed |= {t["name"] for t in seen["home"]["top"] + seen["home"]["trending"]}
        self.assertNotIn("Puddle", listed)
        mine = owner.get("/api/treasures/rankings").get_json()
        self.assertIn("Puddle", {t["name"] for t in mine["home"]["top"]})  # the one who hid it sees it


class DemoTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app("sqlite:///:memory:")
        self.ctx = self.app.app_context()
        self.ctx.push()
        seed_demo_story()
        self.c = self.app.test_client()
        self.c.post("/api/login", json={"username": "demo_player", "password": "demo1234"})

    def tearDown(self):
        db.session.remove()
        self.ctx.pop()

    def test_the_demo_agrees_with_itself(self):
        board = self.c.get("/api/leaderboard").get_json()
        self.assertEqual([r["username"] for r in board], ["demo_player", "ben", "alice"])
        self.assertTrue(all(r["coins"] > 0 for r in board))   # no podium of zeros
        ben = next(r for r in board if r["username"] == "ben")
        self.assertEqual((ben["coins"], ben["found"]), (40, 2))  # two finds and the race bonus
        built_in = next(t for t in self.c.get("/api/treasures").get_json()
                        if t["name"] == "National Tsing Hua University")
        self.assertEqual(built_in["value"]["coins"], 10)  # the pitch shows +10
        feed = self.c.get("/api/feed").get_json()
        posts = feed["posts"] if isinstance(feed, dict) else feed
        self.assertGreater(len({p["ago"] for p in posts}), 2)  # not everything "Just now"
        races = self.c.get("/api/players/demo_player").get_json()["races"]
        self.assertEqual(races[0]["result"], "ben won")


if __name__ == "__main__":
    unittest.main()


class ServiceWorkerTest(unittest.TestCase):
    """B: after an update, the first page load must not use an old saved stylesheet (it looked broken)."""

    def test_styles_and_scripts_come_fresh_when_online(self):
        with open("static/js/sw.js", encoding="utf-8") as f:
            sw = f.read()
        self.assertIn("/\\.(css|js)$/", sw)                                  # styles and scripts...
        self.assertIn("if (code) return fresh.catch(() => saved", sw)        # ...network first, saved copy offline
        self.assertNotIn('VERSION = "stepquest-v1"', sw)                     # old saved copies are thrown away


class StickyTopBarTest(unittest.TestCase):
    """B: the top bar stays at the top while you scroll; things that stick below it use its height."""

    def test_the_top_bar_sticks(self):
        with open("static/css/app.css", encoding="utf-8") as f:
            css = f.read()
        bar = css[css.index("\n.topbar {"):css.index("}", css.index("\n.topbar {"))]
        self.assertIn("position: sticky", bar)
        self.assertIn("top: 0", bar)
        self.assertIn("--topbar-h: 64px", css)
        self.assertIn("top: calc(var(--topbar-h) + 16px)", css)  # Community's side columns
        with open("static/css/styles.css", encoding="utf-8") as f:
            self.assertIn("top: var(--topbar-h)", f.read())      # the home sidebar

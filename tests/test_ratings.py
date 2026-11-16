"""Rating treasures, and the Top rated / Trending this week lists."""

import unittest
from datetime import datetime, timedelta, timezone

from app import create_app
from models import DEMO_TREASURE, Treasure, TreasureRating, db
from ratings import (PRIOR_COUNT, PRIOR_MEAN, can_rate, newest_unrated, parse_stars, summary, top_rated, trending,
                     trending_score, weighted_score)

NOW = datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc)


class TestRules(unittest.TestCase):
    def test_parse_stars(self):
        for stars in (1, 3, 5):
            self.assertEqual(parse_stars({"stars": stars}), stars)
        for data in ({"stars": 0}, {"stars": 6}, {"stars": 4.5}, {"stars": "5"}, {"stars": True}, {}, None):
            with self.subTest(data=data), self.assertRaises(ValueError):
                parse_stars(data)

    def test_only_after_finding_it(self):
        self.assertTrue(can_rate(3, [1, 3]))
        self.assertFalse(can_rate(3, [1, 2]))

    def test_summary(self):
        self.assertEqual(summary(23, 5), {"average": 4.6, "count": 5})
        self.assertEqual(summary(0, 0), {"average": None, "count": 0})

    def test_weighted_score_starts_from_the_prior(self):
        self.assertEqual(weighted_score(0, 0), PRIOR_MEAN)
        self.assertGreater(weighted_score(5, 1), PRIOR_MEAN)
        self.assertEqual(PRIOR_COUNT, 3)

    def test_one_lonely_five_does_not_beat_many_good_ratings(self):
        rows = [{"id": 1, "stars_sum": 5, "count": 1},        # one 5-star rating
                {"id": 2, "stars_sum": 96, "count": 20},      # twenty ratings, average 4.8
                {"id": 3, "stars_sum": 0, "count": 0}]        # never rated: left out
        self.assertEqual(top_rated(rows), [2, 1])

    def test_ties_go_to_more_ratings(self):
        rows = [{"id": 1, "stars_sum": 4, "count": 1}, {"id": 2, "stars_sum": 8, "count": 2}]
        self.assertEqual(top_rated(rows)[0], 2)

    def test_trending_counts_recent_things_more(self):
        self.assertAlmostEqual(trending_score([NOW], NOW), 1.0)
        self.assertLess(trending_score([NOW - timedelta(days=6)], NOW), 0.2)
        self.assertEqual(trending_score([NOW - timedelta(days=8)], NOW), 0)  # older than a week
        self.assertEqual(trending_score([NOW + timedelta(hours=1)], NOW), 0)  # in the future: ignored

    def test_new_ones_are_the_unrated_newest(self):
        self.assertEqual(newest_unrated([1, 2, 3, 4], [2]), [4, 3, 1])
        self.assertEqual(newest_unrated(range(1, 20), [], limit=2), [19, 18])

    def test_trending_order(self):
        events = {1: [NOW - timedelta(days=5)] * 2,                    # two finds, five days ago
                  2: [NOW - timedelta(hours=1)] * 2,                   # two finds, just now
                  3: [NOW - timedelta(days=30)]}                       # nothing this week: left out
        self.assertEqual(trending(events, NOW), [2, 1])


class TestRatingApi(unittest.TestCase):
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

    def find(self, client, t):
        client.post(f"/api/treasures/{t.id}/claim", json={"lat": t.lat, "lon": t.lon})

    def rate(self, client, t, stars):
        return client.post(f"/api/treasures/{t.id}/rating", json={"stars": stars})

    def test_needs_a_login_and_a_real_treasure(self):
        self.assertEqual(self.rate(self.app.test_client(), self.built_in, 5).status_code, 401)
        ann = self.player("ann")
        self.assertEqual(ann.post("/api/treasures/999/rating", json={"stars": 5}).status_code, 404)

    def test_you_must_find_it_first(self):
        ann = self.player("ann")
        r = self.rate(ann, self.built_in, 5)
        self.assertEqual(r.status_code, 403)
        self.assertIn("Find this treasure first", r.get_json()["error"])

    def test_rate_and_change_your_mind(self):
        ann, bob = self.player("ann"), self.player("bob")
        self.find(ann, self.built_in)
        self.find(bob, self.built_in)
        self.assertEqual(self.rate(ann, self.built_in, 5).get_json()["count"], 1)
        r = self.rate(bob, self.built_in, 4).get_json()
        self.assertEqual((r["average"], r["count"], r["mine"]), (4.5, 2, 4))
        r = self.rate(bob, self.built_in, 2).get_json()          # bob changes his mind
        self.assertEqual((r["average"], r["count"]), (3.5, 2))
        self.assertEqual(db.session.query(TreasureRating).count(), 2)

    def test_bad_stars(self):
        ann = self.player("ann")
        self.find(ann, self.built_in)
        self.assertEqual(self.rate(ann, self.built_in, 9).status_code, 400)

    def test_the_treasure_list_shows_stars(self):
        ann = self.player("ann")
        self.find(ann, self.built_in)
        self.rate(ann, self.built_in, 4)
        t = next(t for t in ann.get("/api/treasures").get_json() if t["id"] == self.built_in.id)
        self.assertEqual((t["rating"], t["my_rating"]), ({"average": 4.0, "count": 1}, 4))
        guest = next(t for t in self.app.test_client().get("/api/treasures").get_json()
                     if t["id"] == self.built_in.id)
        self.assertIsNone(guest["my_rating"])

    def test_rankings(self):
        ann = self.player("ann")
        ann.post("/api/treasures", json={"name": "Unloved", "lat": 24.8, "lon": 121.0})
        bob = self.player("bob")
        self.find(bob, self.built_in)
        self.rate(bob, self.built_in, 5)
        data = self.app.test_client().get("/api/treasures/rankings").get_json()  # anyone can see it
        self.assertEqual([t["name"] for t in data["top_rated"]], [DEMO_TREASURE["name"]])
        self.assertEqual(data["top_rated"][0]["rating"], {"average": 5.0, "count": 1})
        self.assertEqual([t["name"] for t in data["trending"]], [DEMO_TREASURE["name"]])
        self.assertEqual(data["trending"][0]["finds_this_week"], 1)
        self.assertEqual([t["name"] for t in data["new"]], ["Unloved"])  # rated ones are not "new"
        self.assertEqual(data["new"][0]["rating"], {"average": None, "count": 0})


class TestPages(unittest.TestCase):
    """The map asks for a rating after a find; the welcome page shows the two lists."""

    def setUp(self):
        self.app = create_app("sqlite:///:memory:")
        client = self.app.test_client()
        client.post("/api/register", json={"username": "ann", "password": "secret1"})  # the map needs a login
        self.map = client.get("/").get_data(as_text=True)
        self.welcome = client.get("/welcome").get_data(as_text=True)

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()
            db.engine.dispose()

    def test_map_rate_box(self):
        self.assertIn('id="rateBox"', self.map)
        self.assertEqual(self.map.count('class="rate-star"'), 5)
        self.assertIn("/rating`", self.map)
        self.assertIn("showRateBox(treasureId, name);", self.map)
        self.assertIn('id="boardStars"', self.map)

    def test_welcome_lists(self):
        self.assertIn("/api/treasures/rankings", self.welcome)
        self.assertIn("Top rated", self.welcome)
        self.assertIn("Trending this week", self.welcome)
        self.assertIn('"New!"', self.welcome)
        self.assertNotIn(".innerHTML", self.welcome)
        self.assertNotIn(".innerHTML", self.map)


if __name__ == "__main__":
    unittest.main()

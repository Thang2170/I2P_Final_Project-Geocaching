"""What a treasure pays right now: supply and demand (treasure_value.py, coin_api.py, map, welcome page)."""

import unittest
from datetime import datetime, timedelta, timezone

from app import create_app
from models import CoinTransaction, Treasure, db
from treasure_value import (BASE_COINS, MAX_COINS, MIN_COINS, coins_for, explain, label)

NOW = datetime(2026, 11, 24, 12, 0, tzinfo=timezone.utc)


def days_ago(n):
    return NOW - timedelta(days=n)


class TestRules(unittest.TestCase):
    def test_a_new_treasure_pays_the_normal_amount(self):
        self.assertEqual(coins_for(NOW, [], NOW), BASE_COINS)

    def test_nobody_found_it_for_a_while(self):
        self.assertEqual(coins_for(days_ago(3), [], NOW), 16)          # +2 a day since it was hidden
        self.assertEqual(coins_for(days_ago(60), [days_ago(5)], NOW), 20)  # +2 a day since the last find
        self.assertEqual(coins_for(days_ago(400), [], NOW), MAX_COINS)  # never more than 30

    def test_popular_this_week(self):
        found = [NOW - timedelta(hours=h) for h in range(1, 7)]  # 6 finds today
        self.assertEqual(coins_for(days_ago(30), found, NOW), BASE_COINS - 4)  # the first 2 are free
        many = [NOW - timedelta(minutes=m) for m in range(1, 40)]
        self.assertEqual(coins_for(days_ago(30), many, NOW), MIN_COINS)  # never less than 5

    def test_old_finds_do_not_make_it_cheap(self):
        old = [days_ago(10 + i) for i in range(20)]  # lots of finds, but not this week
        self.assertEqual(coins_for(days_ago(60), old, NOW), 10 + 2 * 10)

    def test_times_without_a_zone(self):
        self.assertEqual(coins_for(days_ago(3).replace(tzinfo=None), [], NOW), 16)  # SQLite drops the zone

    def test_words(self):
        self.assertEqual((label(24), label(10), label(6)), ("bounty", "", "popular"))
        self.assertIn("nobody has found it", explain(24))
        self.assertEqual(explain(10), "Worth 10 coins.")


class TestApi(unittest.TestCase):
    def setUp(self):
        self.app = create_app("sqlite:///:memory:")
        self.context = self.app.app_context()
        self.context.push()
        self.player = self.app.test_client()
        self.player.post("/api/register", json={"username": "ann", "password": "secret1"})
        self.old = Treasure(name="Forgotten bench", lat=24.79, lon=120.99,
                            created_at=datetime.now(timezone.utc) - timedelta(days=30))
        db.session.add(self.old)
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
        self.context.pop()

    def listed(self):
        return {t["id"]: t for t in self.player.get("/api/treasures").get_json()}

    def test_the_list_shows_the_value(self):
        value = self.listed()[self.old.id]["value"]
        self.assertEqual((value["coins"], value["label"]), (MAX_COINS, "bounty"))
        self.assertIn("nobody has found it", value["note"])

    def test_a_find_pays_the_bounty(self):
        r = self.player.post(f"/api/treasures/{self.old.id}/claim", json={"lat": 24.79, "lon": 120.99})
        self.assertEqual(r.get_json()["coins_earned"], MAX_COINS)
        paid = db.session.execute(db.select(CoinTransaction.amount).filter_by(treasure_id=self.old.id)).scalar_one()
        self.assertEqual(paid, MAX_COINS)
        self.assertEqual(self.listed()[self.old.id]["value"]["coins"], BASE_COINS)  # just found: back to normal

    def test_the_welcome_page_rows_show_the_value(self):
        rankings = self.app.test_client().get("/api/treasures/rankings").get_json()
        values = {t["id"]: t["value"]["coins"] for t in rankings["new"]}
        self.assertEqual(values[self.old.id], MAX_COINS)

    def test_pages(self):
        map_html = self.player.get("/").get_data(as_text=True)
        self.assertIn('id="boardWorth"', map_html)
        self.assertIn("pin--bounty", map_html)
        welcome = self.player.get("/welcome").get_data(as_text=True)
        self.assertIn('id="firstCoins"', welcome)
        self.assertIn("mini-coins", welcome)


if __name__ == "__main__":
    unittest.main()

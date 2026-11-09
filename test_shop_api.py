import unittest

from flask import Flask

from auth_api import auth_api
from coin_api import coin_api, get_balance
from models import CoinTransaction, Purchase, User, db
from shop_api import shop_api


class TestShopApi(unittest.TestCase):
    def setUp(self):
        # A throwaway app with an in-memory database, so tests never touch geohunt.db.
        self.app = Flask(__name__)
        self.app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
        self.app.config["SECRET_KEY"] = "test-key"
        db.init_app(self.app)
        for blueprint in (auth_api, coin_api, shop_api):
            self.app.register_blueprint(blueprint)
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        self.client = self.app.test_client()
        self.client.post("/api/register", json={"username": "bao", "password": "secret1"})

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
        self.context.pop()

    def user_id(self, username="bao"):
        return db.session.query(User).filter_by(username=username).one().id

    def give_coins(self, amount, username="bao"):
        # the coin rules are tested elsewhere: here we just hand out coins (not tied to any treasure)
        db.session.add(CoinTransaction(user_id=self.user_id(username), amount=amount, reason="test_gift"))
        db.session.commit()

    def buy(self, item_id, client=None):
        return (client or self.client).post("/api/shop/buy", json={"item_id": item_id})

    def balance(self):
        return get_balance(self.user_id())

    def test_shop_page_loads(self):
        r = self.client.get("/shop")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"Shop", r.data)

    def test_item_list_is_public(self):
        r = self.app.test_client().get("/api/shop/items")
        self.assertEqual(r.status_code, 200)
        items = r.get_json()
        self.assertGreaterEqual(len(items), 3)
        self.assertTrue(all(not item["owned"] for item in items))

    def test_buying_a_voucher_costs_coins_and_gives_a_code(self):
        self.give_coins(100)
        r = self.buy("bubble-tea")
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertRegex(data["voucher_code"], r"^TH-[A-Z2-9]{6}$")
        self.assertEqual(data["balance"], 50)
        self.assertEqual(self.balance(), 50)

    def test_buying_a_keepsake_has_no_code(self):
        self.give_coins(100)
        data = self.buy("gold-pin").get_json()
        self.assertIsNone(data["voucher_code"])
        self.assertEqual(data["balance"], 60)

    def test_not_enough_coins(self):
        self.give_coins(10)
        r = self.buy("gold-pin")
        self.assertEqual(r.status_code, 402)
        self.assertEqual(self.balance(), 10)
        self.assertEqual(db.session.query(Purchase).count(), 0)

    def test_exactly_enough_coins(self):
        self.give_coins(40)
        self.assertEqual(self.buy("gold-pin").status_code, 200)
        self.assertEqual(self.balance(), 0)

    def test_a_keepsake_cannot_be_bought_twice(self):
        self.give_coins(500)
        self.assertEqual(self.buy("gold-pin").status_code, 200)
        self.assertEqual(self.buy("gold-pin").status_code, 409)
        self.assertEqual(self.balance(), 460)

    def test_a_voucher_can_be_bought_twice_with_different_codes(self):
        self.give_coins(500)
        first = self.buy("cafe-10").get_json()["voucher_code"]
        second = self.buy("cafe-10").get_json()["voucher_code"]
        self.assertNotEqual(first, second)
        self.assertEqual(self.balance(), 440)

    def test_unknown_item(self):
        self.give_coins(500)
        self.assertEqual(self.buy("no-such-thing").status_code, 404)
        self.assertEqual(self.balance(), 500)

    def test_missing_item_id(self):
        for body in [{}, {"item_id": ""}, {"item_id": 5}]:
            with self.subTest(body=body):
                self.assertEqual(self.client.post("/api/shop/buy", json=body).status_code, 400)

    def test_buying_needs_a_login(self):
        r = self.buy("gold-pin", client=self.app.test_client())
        self.assertEqual(r.status_code, 401)
        self.assertEqual(db.session.query(Purchase).count(), 0)

    def test_purchase_list_shows_my_purchases_newest_first(self):
        self.give_coins(500)
        self.buy("gold-pin")
        code = self.buy("bubble-tea").get_json()["voucher_code"]
        rows = self.client.get("/api/shop/purchases").get_json()
        self.assertEqual([r["item_id"] for r in rows], ["bubble-tea", "gold-pin"])
        self.assertEqual(rows[0]["voucher_code"], code)
        self.assertEqual((rows[0]["name"], rows[0]["price"]), ("Free bubble tea", 50))

    def test_purchase_list_needs_a_login(self):
        self.assertEqual(self.app.test_client().get("/api/shop/purchases").status_code, 401)

    def test_items_you_own_are_marked(self):
        self.give_coins(500)
        self.buy("gold-pin")
        self.buy("bubble-tea")
        owned = {i["id"]: i["owned"] for i in self.client.get("/api/shop/items").get_json()}
        self.assertTrue(owned["gold-pin"])
        self.assertFalse(owned["bubble-tea"])  # vouchers can always be bought again

    def test_players_have_separate_purchases_and_coins(self):
        self.give_coins(500)
        self.buy("gold-pin")
        other = self.app.test_client()
        other.post("/api/register", json={"username": "lan", "password": "secret2"})
        self.assertEqual(other.get("/api/shop/purchases").get_json(), [])
        self.assertEqual(other.get("/api/coins").get_json()["balance"], 0)
        self.assertEqual(self.buy("gold-pin", client=other).status_code, 402)

    def test_the_coin_ledger_records_the_spending(self):
        self.give_coins(100)
        self.buy("bubble-tea")
        reasons = [(t.amount, t.reason) for t in db.session.query(CoinTransaction).order_by(CoinTransaction.id)]
        self.assertEqual(reasons, [(100, "test_gift"), (-50, "shop")])

    def test_spending_does_not_change_the_found_treasures_list(self):
        self.give_coins(100)
        self.buy("bubble-tea")
        self.assertEqual(self.client.get("/api/coins").get_json()["found_treasure_ids"], [])


if __name__ == "__main__":
    unittest.main()

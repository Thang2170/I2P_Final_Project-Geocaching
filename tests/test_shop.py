import re
import unittest

from shop import (ALREADY_OWNED, ITEMS, NOT_ENOUGH_COINS, UNKNOWN_ITEM, find_item,
                  item_to_dict, make_voucher_code, purchase_problem)


class TestCatalog(unittest.TestCase):
    def test_ids_are_unique(self):
        ids = [item.id for item in ITEMS]
        self.assertEqual(len(ids), len(set(ids)))

    def test_every_item_has_a_positive_price(self):
        for item in ITEMS:
            with self.subTest(item=item.id):
                self.assertGreater(item.price, 0)

    def test_there_are_both_vouchers_and_keepsakes(self):
        self.assertEqual({item.kind for item in ITEMS}, {"voucher", "item"})

    def test_vouchers_can_be_bought_again_but_keepsakes_cannot(self):
        for item in ITEMS:
            with self.subTest(item=item.id):
                self.assertEqual(item.once, item.kind == "item")

    def test_find_item(self):
        self.assertEqual(find_item("gold-pin").name, "Gold pin")
        self.assertIsNone(find_item("nope"))
        self.assertIsNone(find_item(None))

    def test_item_to_dict(self):
        data = item_to_dict(find_item("gold-pin"))
        self.assertEqual((data["id"], data["price"], data["kind"], data["once"]), ("gold-pin", 40, "item", True))


class TestPurchaseProblem(unittest.TestCase):
    PIN = find_item("gold-pin")        # 40 coins, one per player
    TEA = find_item("bubble-tea")      # 50 coins, repeatable

    def test_enough_coins_is_allowed(self):
        self.assertIsNone(purchase_problem(self.PIN, 100, False))

    def test_exact_price_is_allowed(self):
        self.assertIsNone(purchase_problem(self.PIN, 40, False))

    def test_one_coin_short_is_refused(self):
        self.assertEqual(purchase_problem(self.PIN, 39, False), NOT_ENOUGH_COINS)

    def test_zero_coins_is_refused(self):
        self.assertEqual(purchase_problem(self.TEA, 0, False), NOT_ENOUGH_COINS)

    def test_unknown_item(self):
        self.assertEqual(purchase_problem(None, 1000, False), UNKNOWN_ITEM)

    def test_a_keepsake_cannot_be_bought_twice(self):
        self.assertEqual(purchase_problem(self.PIN, 1000, True), ALREADY_OWNED)

    def test_a_voucher_can_be_bought_twice(self):
        self.assertIsNone(purchase_problem(self.TEA, 1000, True))

    def test_owned_is_reported_before_the_price(self):
        self.assertEqual(purchase_problem(self.PIN, 0, True), ALREADY_OWNED)


class TestVoucherCode(unittest.TestCase):
    def test_format(self):
        for _ in range(50):
            self.assertRegex(make_voucher_code(), r"^TH-[A-HJ-NP-Z2-9]{6}$")

    def test_codes_differ(self):
        self.assertEqual(len({make_voucher_code() for _ in range(200)}), 200)

    def test_no_look_alike_characters(self):
        codes = "".join(make_voucher_code() for _ in range(200))
        self.assertIsNone(re.search(r"[01OI]", codes.replace("TH-", "")))


if __name__ == "__main__":
    unittest.main()

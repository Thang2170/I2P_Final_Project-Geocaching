import unittest
from itertools import combinations

from demo_content import DEMO_FULL_HUNT, DEMO_PASSWORD, DEMO_TREASURES, DEMO_USERS, TREASURE_CREATOR
from hunt_input import parse_hunt
from location import haversine_m
from treasure_input import MIN_TREASURE_GAP_M, parse_treasure
from user_input import parse_new_account
from walk_input import MAX_WEIGHT_KG, MIN_WEIGHT_KG

# the treasure saved by models.seed_demo_data (copied here so this test needs no database)
BUILT_IN = ("National Tsing Hua University", 24.795324, 120.994796)


class TestDemoContent(unittest.TestCase):
    def test_every_demo_account_passes_the_real_signup_rules(self):
        for spec in DEMO_USERS:
            parse_new_account({"username": spec["username"], "password": DEMO_PASSWORD})

    def test_usernames_are_unique(self):
        names = [spec["username"] for spec in DEMO_USERS]
        self.assertEqual(len(names), len(set(names)))

    def test_weights_are_realistic(self):
        for spec in DEMO_USERS:
            self.assertTrue(MIN_WEIGHT_KG <= spec["weight_kg"] <= MAX_WEIGHT_KG, spec["username"])

    def test_every_demo_treasure_passes_the_real_upload_rules(self):
        for spec in DEMO_TREASURES:
            parse_treasure(spec)

    def test_treasures_are_far_enough_apart_to_be_found_one_at_a_time(self):
        points = [(t["name"], t["lat"], t["lon"]) for t in DEMO_TREASURES] + [BUILT_IN]
        for (name_a, lat_a, lon_a), (name_b, lat_b, lon_b) in combinations(points, 2):
            self.assertGreaterEqual(haversine_m(lat_a, lon_a, lat_b, lon_b), MIN_TREASURE_GAP_M,
                                    f"{name_a} and {name_b} are too close")

    def test_treasure_names_are_unique(self):
        names = [t["name"] for t in DEMO_TREASURES] + [BUILT_IN[0]]
        self.assertEqual(len(names), len(set(names)))

    def test_the_treasure_creator_is_a_demo_user(self):
        self.assertIn(TREASURE_CREATOR, [spec["username"] for spec in DEMO_USERS])

    def test_the_full_hunt_passes_the_real_hunt_rules_and_is_full(self):
        parse_hunt({"name": DEMO_FULL_HUNT["name"], "description": DEMO_FULL_HUNT["description"],
                    "capacity": DEMO_FULL_HUNT["capacity"]})
        self.assertEqual(len(DEMO_FULL_HUNT["members"]), DEMO_FULL_HUNT["capacity"])
        usernames = [spec["username"] for spec in DEMO_USERS]
        for member in DEMO_FULL_HUNT["members"]:
            self.assertIn(member, usernames)

    def test_the_login_account_can_afford_something_in_the_shop(self):
        from shop import ITEMS
        player = DEMO_USERS[0]
        self.assertGreaterEqual(player["coins"], min(item.price for item in ITEMS))


if __name__ == "__main__":
    unittest.main()

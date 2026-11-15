import unittest

from coins import (ALREADY_FOUND, COINS_PER_FIND, OWN_TREASURE, TOO_FAR,
                   claim_problem)
from location import FOUND_RADIUS_M


class TestClaimProblem(unittest.TestCase):
    def check(self, distance_m=5, user_id=1, creator_id=2, already_found=False):
        return claim_problem(distance_m, user_id, creator_id, already_found)

    def test_close_enough_is_allowed(self):
        self.assertIsNone(self.check(distance_m=5))

    def test_standing_on_it_is_allowed(self):
        self.assertIsNone(self.check(distance_m=0))

    def test_exactly_at_the_limit_is_allowed(self):
        self.assertIsNone(self.check(distance_m=FOUND_RADIUS_M))

    def test_just_beyond_the_limit_is_too_far(self):
        self.assertEqual(self.check(distance_m=FOUND_RADIUS_M + 0.1), TOO_FAR)

    def test_far_away_is_too_far(self):
        self.assertEqual(self.check(distance_m=500), TOO_FAR)

    def test_your_own_treasure_is_refused(self):
        self.assertEqual(self.check(user_id=2, creator_id=2), OWN_TREASURE)

    def test_demo_treasure_has_no_creator_and_can_be_claimed(self):
        self.assertIsNone(self.check(creator_id=None))

    def test_a_treasure_pays_only_once(self):
        self.assertEqual(self.check(already_found=True), ALREADY_FOUND)

    def test_own_treasure_is_reported_before_the_distance(self):
        self.assertEqual(self.check(distance_m=500, user_id=2, creator_id=2), OWN_TREASURE)

    def test_already_found_is_reported_before_the_distance(self):
        self.assertEqual(self.check(distance_m=500, already_found=True), ALREADY_FOUND)

    def test_a_find_is_worth_ten_coins(self):
        self.assertEqual(COINS_PER_FIND, 10)

    def test_found_radius_is_twenty_meters(self):
        self.assertEqual(FOUND_RADIUS_M, 20)


if __name__ == "__main__":
    unittest.main()

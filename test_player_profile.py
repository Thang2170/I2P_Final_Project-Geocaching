import unittest
from datetime import datetime

from player_profile import joined_label, parse_username, rank_of, walk_totals


class TestParseUsername(unittest.TestCase):
    def test_a_normal_name(self):
        self.assertEqual(parse_username("Ryan_Luong08"), "Ryan_Luong08")

    def test_things_that_cannot_be_a_username(self):
        for value in ("", "ab", "a b", "../admin", "x" * 51, "名字", None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_username(value)


class TestRankOf(unittest.TestCase):
    ROWS = [
        {"username": "ann", "coins": 10, "found": 1, "hidden": 0},
        {"username": "bob", "coins": 30, "found": 3, "hidden": 1},
        {"username": "cyd", "coins": 0, "found": 0, "hidden": 2},
    ]

    def test_same_order_as_the_leaderboard(self):
        self.assertEqual(rank_of("bob", self.ROWS), (1, 3))
        self.assertEqual(rank_of("ann", self.ROWS), (2, 3))
        self.assertEqual(rank_of("cyd", self.ROWS), (3, 3))

    def test_ranks_past_the_top_20_too(self):
        rows = [{"username": f"p{n:02}", "coins": 100 - n, "found": 0, "hidden": 0} for n in range(30)]
        self.assertEqual(rank_of("p29", rows), (30, 30))

    def test_unknown_player(self):
        self.assertEqual(rank_of("zed", self.ROWS), (None, 3))


class TestLabels(unittest.TestCase):
    def test_joined(self):
        self.assertEqual(joined_label(datetime(2026, 11, 4)), "Joined 4 Nov 2026")

    def test_walk_totals(self):
        self.assertEqual(walk_totals([(750, 1000), (1250.4, 1667)]),
                         {"hunts": 2, "distance_km": 2.0, "steps": 2667})
        self.assertEqual(walk_totals([]), {"hunts": 0, "distance_km": 0.0, "steps": 0})


if __name__ == "__main__":
    unittest.main()

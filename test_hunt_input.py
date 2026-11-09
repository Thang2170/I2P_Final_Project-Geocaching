import unittest

from hunt_input import (DEFAULT_CAPACITY, MAX_CAPACITY, parse_capacity,
                        parse_hunt)


class TestParseHunt(unittest.TestCase):
    def test_good_hunt(self):
        self.assertEqual(parse_hunt({"name": " Night walk ", "description": " fun ", "capacity": "5"}),
                         {"name": "Night walk", "description": "fun", "capacity": 5})

    def test_description_and_capacity_are_optional(self):
        clean = parse_hunt({"name": "Walk"})
        self.assertEqual((clean["description"], clean["capacity"]), ("", DEFAULT_CAPACITY))

    def test_empty_capacity_means_the_default(self):
        for blank in [None, "", "   "]:
            with self.subTest(blank=blank):
                self.assertEqual(parse_hunt({"name": "Walk", "capacity": blank})["capacity"], DEFAULT_CAPACITY)

    def test_bad_names_rejected(self):
        for name in ["", "   ", None, 123, "x" * 61]:
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    parse_hunt({"name": name})

    def test_long_description_rejected(self):
        with self.assertRaises(ValueError):
            parse_hunt({"name": "Walk", "description": "x" * 201})

    def test_bad_capacities_rejected(self):
        for capacity in [0, -1, 51, "abc", 2.5, "nan", True]:
            with self.subTest(capacity=capacity):
                with self.assertRaises(ValueError):
                    parse_hunt({"name": "Walk", "capacity": capacity})

    def test_capacity_edges_allowed(self):
        self.assertEqual(parse_capacity(1), 1)
        self.assertEqual(parse_capacity(MAX_CAPACITY), MAX_CAPACITY)
        self.assertEqual(parse_capacity("7.0"), 7)

    def test_non_dict_rejected(self):
        for data in [None, [], "text"]:
            with self.subTest(data=data):
                with self.assertRaises(ValueError):
                    parse_hunt(data)


if __name__ == "__main__":
    unittest.main()

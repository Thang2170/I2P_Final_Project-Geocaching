import unittest

from walk_input import (DEFAULT_WEIGHT_KG, MAX_DISTANCE_M, parse_distance_m,
                        parse_weight_kg)


class TestParseDistance(unittest.TestCase):
    def test_numbers_and_strings(self):
        self.assertEqual(parse_distance_m("750"), 750.0)
        self.assertEqual(parse_distance_m(12.5), 12.5)

    def test_zero_and_the_maximum_are_allowed(self):
        self.assertEqual(parse_distance_m(0), 0.0)
        self.assertEqual(parse_distance_m(MAX_DISTANCE_M), float(MAX_DISTANCE_M))

    def test_bad_values_rejected(self):
        for value in [None, "", "  ", "abc", -1, MAX_DISTANCE_M + 1, "nan", "inf", True]:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    parse_distance_m(value)

    def test_error_names_the_field(self):
        with self.assertRaisesRegex(ValueError, "distance_m"):
            parse_distance_m("abc")


class TestParseWeight(unittest.TestCase):
    def test_good_weights(self):
        self.assertEqual(parse_weight_kg("60"), 60.0)
        self.assertEqual(parse_weight_kg(72.5), 72.5)

    def test_bad_weights_rejected(self):
        for value in [None, "", "abc", 0, 19.9, 300.1, -5, "nan", False]:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    parse_weight_kg(value)

    def test_default_weight_is_itself_valid(self):
        self.assertEqual(parse_weight_kg(DEFAULT_WEIGHT_KG), float(DEFAULT_WEIGHT_KG))


if __name__ == "__main__":
    unittest.main()

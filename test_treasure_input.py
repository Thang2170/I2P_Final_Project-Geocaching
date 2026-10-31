import unittest

from treasure_input import parse_treasure


class TestParseTreasure(unittest.TestCase):
    def good(self, **changes):
        data = {"name": "Library", "description": "Behind the bench", "lat": "24.79", "lon": "120.99"}
        data.update(changes)
        return data

    def test_good_input_is_cleaned(self):
        clean = parse_treasure(self.good(name="  Library  "))
        self.assertEqual(clean, {"name": "Library", "description": "Behind the bench",
                                 "lat": 24.79, "lon": 120.99})

    def test_numbers_and_strings_both_work(self):
        clean = parse_treasure(self.good(lat=24.79, lon=120.99))
        self.assertEqual(clean["lat"], 24.79)

    def test_description_is_optional(self):
        data = self.good()
        del data["description"]
        self.assertEqual(parse_treasure(data)["description"], "")

    def test_missing_or_blank_name_rejected(self):
        for name in ["", "   ", None]:
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    parse_treasure(self.good(name=name))

    def test_name_too_long_rejected(self):
        with self.assertRaises(ValueError):
            parse_treasure(self.good(name="x" * 101))

    def test_description_too_long_rejected(self):
        with self.assertRaises(ValueError):
            parse_treasure(self.good(description="x" * 301))

    def test_bad_coordinates_rejected(self):
        bad_values = [("lat", "abc"), ("lat", ""), ("lat", None), ("lat", 91), ("lat", -90.1),
                      ("lon", 181), ("lon", "nan"), ("lon", "inf"), ("lat", True)]
        for field, value in bad_values:
            with self.subTest(field=field, value=value):
                with self.assertRaises(ValueError):
                    parse_treasure(self.good(**{field: value}))

    def test_edge_coordinates_allowed(self):
        clean = parse_treasure(self.good(lat=90, lon=-180))
        self.assertEqual((clean["lat"], clean["lon"]), (90.0, -180.0))

    def test_missing_coordinate_rejected(self):
        data = self.good()
        del data["lon"]
        with self.assertRaises(ValueError):
            parse_treasure(data)

    def test_non_dict_rejected(self):
        for data in [None, [], "text"]:
            with self.subTest(data=data):
                with self.assertRaises(ValueError):
                    parse_treasure(data)

    def test_non_text_name_rejected(self):
        with self.assertRaises(ValueError):
            parse_treasure(self.good(name=123))


if __name__ == "__main__":
    unittest.main()

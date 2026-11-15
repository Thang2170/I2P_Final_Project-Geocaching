import unittest

from location import haversine_m


class TestHaversine(unittest.TestCase):
    def test_same_point_is_zero(self):
        self.assertEqual(haversine_m(25.0330, 121.5654, 25.0330, 121.5654), 0)

    def test_one_degree_of_latitude(self):
        # One degree of latitude is about 111.2 km everywhere on Earth
        distance = haversine_m(0, 0, 1, 0)
        self.assertAlmostEqual(distance, 111_195, delta=100)

    def test_taipei_101_to_taipei_main_station(self):
        # A real route: about 5.1 km in a straight line
        distance = haversine_m(25.0330, 121.5654, 25.0478, 121.5170)
        self.assertAlmostEqual(distance, 5_146, delta=0.5)


if __name__ == "__main__":
    unittest.main()
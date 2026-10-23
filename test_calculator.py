import unittest

from calculator import calories_from_distance, steps_from_distance


class TestCalculator(unittest.TestCase):
    def test_steps(self):
        self.assertEqual(steps_from_distance(750), 1000)

    def test_zero_distance(self):
        self.assertEqual(steps_from_distance(0), 0)

    def test_calories_one_km(self):
        self.assertAlmostEqual(calories_from_distance(1000, 60), 30.0)

    def test_calories_five_km(self):
        self.assertAlmostEqual(calories_from_distance(5000, 70), 175.0)

    def test_steps_returns_whole_number(self):
        self.assertIsInstance(steps_from_distance(100), int)

    def test_negative_distance_rejected(self):
        with self.assertRaises(ValueError):
            steps_from_distance(-5)


if __name__ == "__main__":
    unittest.main()
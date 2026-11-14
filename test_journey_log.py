import unittest

from journey_log import (MAX_AVG_SPEED_MS, NO_PACE, format_duration, format_pace, parse_journey,
                         rank_players, speed_problem)

GOOD = {"treasure_id": 3, "distance_m": 420, "duration_s": 560, "lat": 24.79, "lon": 120.99}


class TestParseJourney(unittest.TestCase):
    def test_accepts_a_good_hunt(self):
        self.assertEqual(parse_journey(GOOD), GOOD)

    def test_accepts_numbers_sent_as_text(self):
        data = {key: str(value) for key, value in GOOD.items()}
        self.assertEqual(parse_journey(data), GOOD)

    def test_duration_is_rounded_to_whole_seconds(self):
        self.assertEqual(parse_journey({**GOOD, "duration_s": 12.6})["duration_s"], 13)

    def test_zero_distance_is_fine(self):
        self.assertEqual(parse_journey({**GOOD, "distance_m": 0})["distance_m"], 0)

    def test_rejects_every_bad_field(self):
        bad = [("treasure_id", None), ("treasure_id", 0), ("treasure_id", 1.5), ("treasure_id", "abc"),
               ("treasure_id", True), ("distance_m", -1), ("distance_m", 999_999), ("distance_m", "x"),
               ("distance_m", float("nan")), ("duration_s", 0), ("duration_s", 90_000),
               ("lat", 91), ("lon", 181), ("lat", ""), ("lon", None)]
        for field, value in bad:
            with self.subTest(field=field, value=value):
                with self.assertRaises(ValueError):
                    parse_journey({**GOOD, field: value})

    def test_rejects_a_missing_field(self):
        for field in GOOD:
            with self.subTest(field=field):
                data = dict(GOOD)
                del data[field]
                with self.assertRaises(ValueError):
                    parse_journey(data)

    def test_rejects_something_that_is_not_a_dict(self):
        for data in (None, [], "hunt", 5):
            with self.subTest(data=data):
                with self.assertRaises(ValueError):
                    parse_journey(data)


class TestSpeed(unittest.TestCase):
    def test_walking_and_running_are_fine(self):
        self.assertIsNone(speed_problem(1000, 700))   # a brisk walk
        self.assertIsNone(speed_problem(1000, 300))   # a run

    def test_exactly_the_limit_is_fine(self):
        self.assertIsNone(speed_problem(MAX_AVG_SPEED_MS * 100, 100))

    def test_a_car_is_not_a_hunt(self):
        self.assertIn("too fast", speed_problem(5000, 200))


class TestFormatting(unittest.TestCase):
    def test_duration(self):
        self.assertEqual(format_duration(0), "00:00")
        self.assertEqual(format_duration(65), "01:05")
        self.assertEqual(format_duration(3600), "1:00:00")
        self.assertEqual(format_duration(3725), "1:02:05")

    def test_pace_is_minutes_and_seconds_per_km(self):
        self.assertEqual(format_pace(1000, 360), "6:00")
        self.assertEqual(format_pace(500, 215), "7:10")

    def test_short_walks_have_no_pace(self):
        self.assertEqual(format_pace(19, 30), NO_PACE)
        self.assertEqual(format_pace(0, 30), NO_PACE)

    def test_a_crawl_has_no_pace(self):
        self.assertEqual(format_pace(20, 86_400), NO_PACE)


class TestRanking(unittest.TestCase):
    def rows(self, *items):
        return [{"username": name, "hunts": hunts, "distance_m": dist} for name, hunts, dist in items]

    def test_more_hunts_first_then_more_distance(self):
        ranked = rank_players(self.rows(("cy", 1, 900), ("ann", 2, 100), ("bo", 2, 500)))
        self.assertEqual([(r["username"], r["rank"]) for r in ranked], [("bo", 1), ("ann", 2), ("cy", 3)])

    def test_ties_share_a_rank_and_the_next_one_skips(self):
        ranked = rank_players(self.rows(("a", 3, 1000), ("b", 3, 1004), ("c", 2, 50)))
        self.assertEqual([r["rank"] for r in ranked], [1, 1, 3])

    def test_ties_are_listed_by_name(self):
        ranked = rank_players(self.rows(("zed", 1, 100), ("Amy", 1, 100)))
        self.assertEqual([r["username"] for r in ranked], ["Amy", "zed"])

    def test_nobody_gives_an_empty_list(self):
        self.assertEqual(rank_players([]), [])

    def test_does_not_change_the_input(self):
        rows = self.rows(("a", 1, 10))
        rank_players(rows)
        self.assertNotIn("rank", rows[0])


if __name__ == "__main__":
    unittest.main()

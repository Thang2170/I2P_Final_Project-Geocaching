import unittest
from datetime import datetime, timedelta, timezone

from live_positions import LIVE_WINDOW_S, as_utc, is_live, parse_position, seconds_ago

NOW = datetime(2026, 11, 20, 12, 0, 0, tzinfo=timezone.utc)


class TestLivePositions(unittest.TestCase):
    def test_seconds_ago(self):
        self.assertEqual(seconds_ago(NOW - timedelta(seconds=42), NOW), 42)

    def test_time_without_a_zone_counts_as_utc(self):
        # SQLite gives times back without a zone
        naive = datetime(2026, 11, 20, 11, 59, 0)
        self.assertEqual(as_utc(naive).tzinfo, timezone.utc)
        self.assertEqual(seconds_ago(naive, NOW), 60)

    def test_recent_position_is_live(self):
        self.assertTrue(is_live(NOW - timedelta(seconds=10), NOW))
        self.assertTrue(is_live(NOW - timedelta(seconds=LIVE_WINDOW_S), NOW))  # the edge still counts

    def test_old_position_is_hidden(self):
        self.assertFalse(is_live(NOW - timedelta(seconds=LIVE_WINDOW_S + 1), NOW))
        self.assertFalse(is_live(NOW - timedelta(hours=3), NOW))

    def test_parse_good_position(self):
        self.assertEqual(parse_position({"lat": 24.7953, "lon": "120.9948"}), (24.7953, 120.9948))

    def test_parse_bad_positions(self):
        for data in [None, "24,120", {}, {"lat": 24.79}, {"lat": "abc", "lon": 1},
                     {"lat": 95, "lon": 0}, {"lat": 0, "lon": 200}]:
            with self.subTest(data=data):
                with self.assertRaises(ValueError):
                    parse_position(data)


if __name__ == "__main__":
    unittest.main()

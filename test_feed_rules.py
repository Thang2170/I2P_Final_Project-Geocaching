import unittest
from datetime import datetime, timedelta, timezone

from feed_rules import (AVATAR_COLOURS, MAX_COMMENT_CHARS, MAX_POST_CHARS, avatar, like_summary, parse_comment,
                        parse_offset, parse_post, time_ago)

NOW = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)


class TestParsePost(unittest.TestCase):
    def test_keeps_the_text_without_outer_spaces(self):
        self.assertEqual(parse_post({"text": "  Found it!  "}), "Found it!")

    def test_keeps_line_breaks_inside(self):
        self.assertEqual(parse_post({"text": "line 1\nline 2"}), "line 1\nline 2")

    def test_empty_or_missing_text_is_refused(self):
        for data in ({"text": ""}, {"text": "   \n "}, {}, {"text": None}, {"text": 5}, None, "hi"):
            with self.subTest(data=data), self.assertRaises(ValueError):
                parse_post(data)

    def test_the_length_limit(self):
        self.assertEqual(len(parse_post({"text": "a" * MAX_POST_CHARS})), MAX_POST_CHARS)
        with self.assertRaises(ValueError) as err:
            parse_post({"text": "a" * (MAX_POST_CHARS + 1)})
        self.assertIn(str(MAX_POST_CHARS), str(err.exception))

    def test_comments_have_a_shorter_limit(self):
        self.assertEqual(parse_comment({"text": " nice "}), "nice")
        with self.assertRaises(ValueError):
            parse_comment({"text": "a" * (MAX_COMMENT_CHARS + 1)})


class TestParseOffset(unittest.TestCase):
    def test_empty_means_the_top(self):
        for value in (None, "", "  "):
            with self.subTest(value=value):
                self.assertEqual(parse_offset(value), 0)

    def test_a_number(self):
        self.assertEqual(parse_offset("20"), 20)

    def test_bad_values(self):
        for value in ("-1", "x", "2.5"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_offset(value)


class TestAvatar(unittest.TestCase):
    def test_first_letter_in_capitals(self):
        self.assertEqual(avatar("alice")["letter"], "A")

    def test_the_same_name_always_gets_the_same_colour(self):
        self.assertEqual(avatar("ben"), avatar("ben"))
        self.assertIn(avatar("ben")["colour"], range(AVATAR_COLOURS))

    def test_different_names_can_get_different_colours(self):
        colours = {avatar(name)["colour"] for name in ("alice", "ben", "cyd", "dora", "eve", "fred")}
        self.assertGreater(len(colours), 1)

    def test_empty_name(self):
        self.assertEqual(avatar("")["letter"], "?")


class TestTimeAgo(unittest.TestCase):
    def ago(self, **delta):
        return time_ago(NOW - timedelta(**delta), now=NOW)

    def test_steps(self):
        self.assertEqual(self.ago(seconds=10), "Just now")
        self.assertEqual(self.ago(minutes=5), "5 min")
        self.assertEqual(self.ago(hours=3), "3 h")
        self.assertEqual(self.ago(days=2), "2 d")
        self.assertEqual(self.ago(days=30), "15 Oct")

    def test_times_from_sqlite_have_no_time_zone(self):
        then = (NOW - timedelta(minutes=2)).replace(tzinfo=None)
        self.assertEqual(time_ago(then, now=NOW), "2 min")

    def test_a_time_a_bit_in_the_future_is_just_now(self):
        self.assertEqual(time_ago(NOW + timedelta(seconds=5), now=NOW), "Just now")


class TestLikeSummary(unittest.TestCase):
    def test_nobody(self):
        self.assertEqual(like_summary([], False), "")

    def test_others_only(self):
        self.assertEqual(like_summary(["ben"], False), "ben")
        self.assertEqual(like_summary(["ben", "cyd"], False), "ben and cyd")
        self.assertEqual(like_summary(["ben", "cyd", "dora"], False), "ben and 2 others")

    def test_with_you(self):
        self.assertEqual(like_summary([], True), "You")
        self.assertEqual(like_summary(["ben"], True), "You and ben")
        self.assertEqual(like_summary(["ben", "cyd"], True), "You and 2 others")


if __name__ == "__main__":
    unittest.main()

import unittest

from hunt_chat import MAX_MESSAGE_CHARS, can_chat, parse_after, parse_message


class TestParseMessage(unittest.TestCase):
    def test_keeps_the_text_without_outer_spaces(self):
        self.assertEqual(parse_message({"text": "  Meet at the gate  "}), "Meet at the gate")

    def test_empty_or_missing_is_refused(self):
        for data in ({"text": ""}, {"text": "   "}, {}, {"text": None}, {"text": 3}, None, "hi"):
            with self.subTest(data=data), self.assertRaises(ValueError):
                parse_message(data)

    def test_the_length_limit(self):
        self.assertEqual(len(parse_message({"text": "a" * MAX_MESSAGE_CHARS})), MAX_MESSAGE_CHARS)
        with self.assertRaises(ValueError) as err:
            parse_message({"text": "a" * (MAX_MESSAGE_CHARS + 1)})
        self.assertIn(str(MAX_MESSAGE_CHARS), str(err.exception))


class TestParseAfter(unittest.TestCase):
    def test_empty_means_the_latest(self):
        for value in (None, "", " "):
            with self.subTest(value=value):
                self.assertEqual(parse_after(value), 0)

    def test_a_number(self):
        self.assertEqual(parse_after("12"), 12)

    def test_bad_values(self):
        for value in ("-1", "x", "1.5"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_after(value)


class TestCanChat(unittest.TestCase):
    def test_members_can_chat(self):
        self.assertTrue(can_chat(2, [1, 2, 3]))

    def test_others_cannot(self):
        self.assertFalse(can_chat(9, [1, 2, 3]))
        self.assertFalse(can_chat(1, []))


if __name__ == "__main__":
    unittest.main()

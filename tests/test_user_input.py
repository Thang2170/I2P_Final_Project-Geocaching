import unittest

from user_input import parse_login, parse_new_account


class TestParseNewAccount(unittest.TestCase):
    def test_good_account(self):
        self.assertEqual(parse_new_account({"username": "  bao_1 ", "password": "secret1"}),
                         ("bao_1", "secret1"))

    def test_bad_usernames_rejected(self):
        for name in ["", "ab", "has space", "bad!", "x" * 51, None, "ünï", "a-b"]:
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    parse_new_account({"username": name, "password": "secret1"})

    def test_username_edges_allowed(self):
        parse_new_account({"username": "abc", "password": "secret1"})
        parse_new_account({"username": "x" * 50, "password": "secret1"})

    def test_short_password_rejected(self):
        with self.assertRaises(ValueError):
            parse_new_account({"username": "bao", "password": "12345"})

    def test_long_password_rejected(self):
        with self.assertRaises(ValueError):
            parse_new_account({"username": "bao", "password": "x" * 129})

    def test_password_is_not_trimmed(self):
        self.assertEqual(parse_new_account({"username": "bao", "password": " pass12 "})[1], " pass12 ")

    def test_non_text_rejected(self):
        for data in [{"username": 123, "password": "secret1"}, {"username": "bao", "password": 123456}, None, []]:
            with self.subTest(data=data):
                with self.assertRaises(ValueError):
                    parse_new_account(data)


class TestParseLogin(unittest.TestCase):
    def test_good_login(self):
        self.assertEqual(parse_login({"username": " bao ", "password": "x"}), ("bao", "x"))

    def test_missing_parts_rejected(self):
        for data in [{}, {"username": "bao"}, {"password": "x"}, {"username": "  ", "password": "x"}]:
            with self.subTest(data=data):
                with self.assertRaises(ValueError):
                    parse_login(data)

    def test_old_short_passwords_can_still_be_tried(self):
        # login does not enforce the new-account rules
        parse_login({"username": "bao", "password": "x"})


if __name__ == "__main__":
    unittest.main()

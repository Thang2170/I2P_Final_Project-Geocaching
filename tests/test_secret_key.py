"""Login cookies are signed with a key nobody else knows (see secret_key.py)."""

import os
import unittest

from app import create_app
from models import db
from secret_key import MIN_KEY_LENGTH, choose_secret_key, new_key
from tests import PROJECT_ROOT


class TestChooseSecretKey(unittest.TestCase):
    def test_the_environment_variable_wins(self):
        self.assertEqual(choose_secret_key("from-env", "x" * 64), ("from-env", False))

    def test_a_saved_key_is_reused(self):
        saved = "a" * 64
        self.assertEqual(choose_secret_key(None, saved + "\n"), (saved, False))

    def test_no_key_yet_makes_one_to_save(self):
        key, must_save = choose_secret_key(None, None)
        self.assertTrue(must_save)
        self.assertGreaterEqual(len(key), MIN_KEY_LENGTH)

    def test_a_too_short_saved_key_is_replaced(self):
        key, must_save = choose_secret_key("  ", "short")
        self.assertTrue(must_save)
        self.assertNotEqual(key, "short")

    def test_new_keys_are_random(self):
        self.assertNotEqual(new_key(), new_key())


class TestAppKey(unittest.TestCase):
    def test_the_old_public_key_is_gone(self):
        with open(os.path.join(PROJECT_ROOT, "app.py"), encoding="utf-8") as f:
            self.assertNotIn("dev-only-change-me", f.read())

    def test_each_test_app_gets_its_own_random_key(self):
        apps = [create_app("sqlite:///:memory:") for _ in range(2)]
        try:
            keys = [a.config["SECRET_KEY"] for a in apps]
            self.assertNotEqual(keys[0], keys[1])
            self.assertGreaterEqual(len(keys[0]), MIN_KEY_LENGTH)
        finally:
            for a in apps:
                with a.app_context():
                    db.session.remove()
                    db.drop_all()
                    db.engine.dispose()


if __name__ == "__main__":
    unittest.main()

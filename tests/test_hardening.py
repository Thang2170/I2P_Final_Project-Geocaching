"""B: the second polish round: password guessing, weak passwords, the secure cookie, compression,
labels and headings, and text colours that are easy to read."""

import gzip
import os
import re
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from app import create_app
from gzip_responses import should_compress, wants_gzip
from login_guard import MAX_FAILS, WINDOW_S, lock_text, locked_for, tries_left_text
from models import LoginFailure, db
from user_input import parse_new_account, weak_password


def _utc_now():
    """Naive UTC, like the database keeps (datetime.utcnow() is deprecated in Python 3.12+)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)

T0 = datetime(2026, 11, 27, 12, 0, 0)


class GuardRulesTest(unittest.TestCase):
    def test_locked_after_five_wrong_tries(self):
        tries = [T0 + timedelta(seconds=i) for i in range(MAX_FAILS - 1)]
        self.assertEqual(locked_for(tries, T0 + timedelta(seconds=10)), 0)
        tries.append(T0 + timedelta(seconds=4))
        self.assertEqual(locked_for(tries, T0 + timedelta(seconds=10)), WINDOW_S - 10)

    def test_old_tries_stop_counting(self):
        tries = [T0 + timedelta(seconds=i) for i in range(MAX_FAILS)]
        self.assertEqual(locked_for(tries, T0 + timedelta(seconds=WINDOW_S)), 0)

    def test_texts(self):
        self.assertEqual(lock_text(30), "Too many wrong passwords. Try again in 1 minute.")
        self.assertEqual(lock_text(540), "Too many wrong passwords. Try again in 9 minutes.")
        self.assertEqual(tries_left_text(1), "")
        self.assertIn("2 more tries", tries_left_text(MAX_FAILS - 2))
        self.assertIn("1 more try", tries_left_text(MAX_FAILS - 1))


class PasswordRulesTest(unittest.TestCase):
    def test_weak_passwords(self):
        for pw in ("123456", "Password", "qwerty123", "5201314", "aaaaaaa"):
            with self.assertRaises(ValueError):
                parse_new_account({"username": "mei", "password": pw})
        self.assertIn("username", weak_password("ben", "ben12345"))
        self.assertIsNone(weak_password("mei", "pond-at-dawn"))
        self.assertEqual(parse_new_account({"username": "demo_player", "password": "demo1234"})[1], "demo1234")


class LoginApiTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app("sqlite:///:memory:")
        self.ctx = self.app.app_context()
        self.ctx.push()
        self.app.test_client().post("/api/register", json={"username": "ann", "password": "secret1"})

    def tearDown(self):
        db.session.remove()
        self.ctx.pop()

    def login(self, password, place="10.0.0.1", name="ann"):
        return self.app.test_client().post("/api/login", json={"username": name, "password": password},
                                           environ_base={"REMOTE_ADDR": place})

    def test_five_wrong_passwords_lock_the_username_there(self):
        for i in range(MAX_FAILS - 1):
            self.assertEqual(self.login("nope").status_code, 401)
        last = self.login("nope")  # the last allowed try already says it is locked
        self.assertEqual(last.status_code, 429)
        self.assertIn("Try again in 10 minutes", last.get_json()["error"])
        locked = self.login("secret1")  # even the right password waits
        self.assertEqual(locked.status_code, 429)
        self.assertIn("Too many wrong passwords", locked.get_json()["error"])
        self.assertGreater(int(locked.headers["Retry-After"]), 0)
        self.assertEqual(self.login("secret1", place="10.0.0.2").status_code, 200)  # the real player elsewhere

    def test_the_warning_comes_before_the_lock(self):
        messages = [self.login("nope").get_json()["error"] for _ in range(MAX_FAILS)]
        self.assertEqual(messages[0], "Wrong username or password.")
        self.assertIn("2 more tries", messages[MAX_FAILS - 3])
        self.assertIn("1 more try", messages[MAX_FAILS - 2])
        self.assertIn("Too many wrong passwords", messages[MAX_FAILS - 1])

    def test_a_right_password_clears_the_count(self):
        for _ in range(MAX_FAILS - 1):
            self.login("nope")
        self.assertEqual(self.login("secret1").status_code, 200)
        self.assertEqual(db.session.query(LoginFailure).count(), 0)
        self.assertEqual(self.login("nope").status_code, 401)  # counting starts again

    def test_the_lock_ends(self):
        for _ in range(MAX_FAILS):
            self.login("nope")
        later = _utc_now() + timedelta(seconds=WINDOW_S + 1)
        with patch("auth_api._now", return_value=later):
            self.assertEqual(self.login("secret1").status_code, 200)

    def test_unknown_usernames_look_the_same(self):
        for _ in range(MAX_FAILS - 1):
            self.assertEqual(self.login("nope", name="ghost").status_code, 401)
        self.assertEqual(self.login("nope", name="ghost").status_code, 429)


class CookieTest(unittest.TestCase):
    def test_secure_outside_tests(self):
        self.assertFalse(create_app("sqlite:///:memory:").config["SESSION_COOKIE_SECURE"])  # tests use http
        # ignore_cleanup_errors: Windows cannot delete a database file that is still open.
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
            uri = "sqlite:///" + os.path.join(folder, "t.db")
            real = create_app(uri)
            with patch.dict(os.environ, {"STEPQUEST_HTTP": "1"}):
                plain_http = create_app(uri)
            self.assertTrue(real.config["SESSION_COOKIE_SECURE"])
            self.assertFalse(plain_http.config["SESSION_COOKIE_SECURE"])
            for app in (real, plain_http):
                with app.app_context():
                    db.session.remove()
                    db.engine.dispose()  # close the file before the folder is removed


class CompressionTest(unittest.TestCase):
    def test_rules(self):
        self.assertTrue(wants_gzip("gzip, deflate, br"))
        self.assertFalse(wants_gzip("br"))
        self.assertFalse(wants_gzip(None))
        self.assertTrue(should_compress("text/css", 5000, 200, False, "gzip"))
        self.assertFalse(should_compress("text/css", 500, 200, False, "gzip"))      # too small to bother
        self.assertFalse(should_compress("image/png", 5000, 200, False, "gzip"))    # already compressed
        self.assertFalse(should_compress("text/css", 5000, 304, False, "gzip"))
        self.assertFalse(should_compress("text/css", 5000, 200, True, "gzip"))      # already encoded

    def test_styles_arrive_gzipped_and_unchanged(self):
        c = create_app("sqlite:///:memory:").test_client()
        plain = c.get("/static/css/sprites.css").data
        packed = c.get("/static/css/sprites.css", headers={"Accept-Encoding": "gzip"})
        self.assertEqual(packed.headers["Content-Encoding"], "gzip")
        self.assertIn("Accept-Encoding", packed.headers["Vary"])
        self.assertEqual(gzip.decompress(packed.data), plain)
        self.assertLess(len(packed.data), len(plain) / 4)
        self.assertNotIn("Content-Encoding", c.get("/static/css/sprites.css").headers)  # no gzip asked for


class PagesTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app("sqlite:///:memory:")
        self.c = self.app.test_client()
        self.c.post("/api/register", json={"username": "ann", "password": "secret1"})

    def test_labels_and_the_map_heading(self):
        self.assertIn('<label for="deviceName"', self.c.get("/health").get_data(as_text=True))
        self.assertIn('<label for="code"', self.c.get("/scan").get_data(as_text=True))
        self.assertIn('<h1 class="visually-hidden">Map</h1>', self.c.get("/").get_data(as_text=True))

    def test_health_answers_go_under_their_form(self):
        html = self.c.get("/health").get_data(as_text=True)
        self.assertIn("function showAt(form, text, ok)", html)
        self.assertEqual(html.count("showAt(event.target"), 6)  # age, pairing and delete: success and error


class ContrastTest(unittest.TestCase):
    @staticmethod
    def ratio(a, b):
        def lum(h):
            r, g, bl = (int(h[i:i + 2], 16) / 255 for i in (1, 3, 5))
            f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
            return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(bl)
        hi, lo = sorted((lum(a), lum(b)), reverse=True)
        return (hi + 0.05) / (lo + 0.05)

    def test_text_colours_pass_on_the_page_background(self):
        with open("static/css/pixel.css", encoding="utf-8") as f:
            css = f.read()
        colour = lambda name: re.search(rf"--px-{name}: (#[0-9a-f]{{6}})", css).group(1)
        for name in ("ink", "muted", "gold-dark", "good", "bad"):
            self.assertGreaterEqual(self.ratio(colour(name), colour("bg")), 4.5, name)


if __name__ == "__main__":
    unittest.main()


class StandardLibraryNamesTest(unittest.TestCase):
    """B: a project file named like a Python module hides that module (compression.py broke gzip on 3.14)."""

    NEW_IN_PYTHON_3_14 = {"compression", "annotationlib"}  # not yet in older Pythons' list

    def test_no_file_takes_a_standard_library_name(self):
        import sys
        taken = set(sys.stdlib_module_names) | self.NEW_IN_PYTHON_3_14
        ours = {name[:-3] for name in os.listdir(".") if name.endswith(".py")}
        self.assertEqual(sorted(ours & taken), [])

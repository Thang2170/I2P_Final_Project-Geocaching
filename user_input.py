"""Check the username and password a player sends. Owner: B.

Plain Python with no Flask and no database, so it is easy to test.
"""

import re

USERNAME_PATTERN = re.compile(r"[A-Za-z0-9_]{3,50}")
MIN_PASSWORD_LENGTH = 6
MAX_PASSWORD_LENGTH = 128


def _text_field(data, field):
    if not isinstance(data, dict):
        raise ValueError("Send the details as JSON or form data")
    value = data.get(field)
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise ValueError(f"{field} must be text")
    return value


def parse_new_account(data):
    """Return (username, password) for a new account, or raise ValueError."""
    username = _text_field(data, "username").strip()
    password = _text_field(data, "password")

    if not USERNAME_PATTERN.fullmatch(username):
        raise ValueError("username must be 3 to 50 letters, numbers or underscores")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"password must be at least {MIN_PASSWORD_LENGTH} characters")
    if len(password) > MAX_PASSWORD_LENGTH:
        raise ValueError(f"password must be at most {MAX_PASSWORD_LENGTH} characters")
    problem = weak_password(username, password)
    if problem:
        raise ValueError(problem)
    return username, password


# B: passwords people guess first (worldwide lists, plus ones common in Taiwan such as 5201314).
COMMON_PASSWORDS = frozenset("""
123456 1234567 12345678 123456789 1234567890 654321 987654321 123123 123321 112233 121212 111111 000000
666666 888888 11111111 00000000 88888888 147258 147258369 159753 7758521 5201314 1314520 woaini
password password1 password123 passw0rd qwerty qwerty123 qwertyuiop 1qaz2wsx 1q2w3e 1q2w3e4r 1234qwer
abc123 abcdef abcd1234 a123456 aa123456 a12345678 asdfgh zxcvbn iloveyou letmein welcome admin
admin123 football baseball monkey dragon sunshine princess master hello123 shadow superman starwars
trustno1 michael charlie
""".split())


def weak_password(username, password):
    """B: why this password is too easy to guess, or None if it is fine."""
    lowered = password.lower()
    if lowered in COMMON_PASSWORDS:
        return "That password is one of the first ones people guess. Choose something less common."
    if lowered == username.lower() or username.lower() in lowered:
        return "Your password must not contain your username."
    if len(set(password)) == 1:
        return "Use more than one kind of character in your password."
    return None


def parse_login(data):
    """Return (username, password) for a login attempt, or raise ValueError.

    Only checks that both are there. Whether they are right is decided later,
    with one message for every failure so we never reveal which usernames exist.
    """
    username = _text_field(data, "username").strip()
    password = _text_field(data, "password")
    if not username or not password:
        raise ValueError("Enter your username and password")
    return username, password

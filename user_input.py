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
    return username, password


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

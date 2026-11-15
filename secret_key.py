"""Which key signs the login cookies (owner: B).

The key used to be the fixed text "dev-only-change-me", which is public in the repo, so anyone
could forge a login cookie (even for an admin) when the app is shared over ngrok.
Now the app uses, in this order:
1. the SECRET_KEY environment variable, if it is set (for a real deployment), or
2. a random key made once and kept in instance/secret_key (git ignores instance/),
   so logins survive restarting the app, but nobody else knows the key.

choose_secret_key() is plain Python with no Flask, so it is easy to test;
create_app() in app.py does the reading and saving of the file.
"""

import secrets

KEY_FILE = "secret_key"
MIN_KEY_LENGTH = 32


def new_key():
    """A long random key (64 hex characters)."""
    return secrets.token_hex(32)


def choose_secret_key(env_value, saved_value):
    """Return (key, must_save).

    env_value: the SECRET_KEY environment variable, or None.
    saved_value: what instance/secret_key holds, or None if there is no such file.
    must_save is True when a new key was made and should be written to the file.
    """
    if env_value and env_value.strip():
        return env_value.strip(), False
    if saved_value and len(saved_value.strip()) >= MIN_KEY_LENGTH:
        return saved_value.strip(), False
    return new_key(), True  # no key yet (or a too-short one): make one and keep it

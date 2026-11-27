"""The box that proves you were there: a 6-number code that changes every 30 seconds (owner: B).

A real box at the treasure (the ESP32, esp32/box_main.py) shows the code on its screen.
The server works out the same code from the same secret, so only someone standing at the
box can type it. A GPS position can be faked; this code cannot be guessed.

It is the same maths as phone authenticator apps (HOTP, RFC 4226, on a 30-second clock as in
RFC 6238). esp32/box_math.py does the same sums on the ESP32; a test checks they agree.

Plain Python with no Flask and no database, so it is easy to test.
"""

import hashlib
import hmac
import secrets
import struct

STEP_S = 30          # a new code every 30 seconds
DIGITS = 6
DRIFT_STEPS = 1      # also accept the code just before and just after (a slow typist, a slow clock)
SECRET_BYTES = 20    # 160 bits, like authenticator apps

BAD_CODE = "Type the 6 numbers shown on the box."
WRONG_CODE = "That is not the code on the box right now. Check the screen and try again."
CODE_USED = "Someone else just used that code. Wait for the next one (at most 30 seconds)."


def new_secret():
    """A new random secret for a box, as hex (it goes in the ESP32's config.py)."""
    return secrets.token_hex(SECRET_BYTES)


def hotp(key, counter, digits=DIGITS):
    """RFC 4226: the code for this counter, as text with leading zeros."""
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    start = digest[-1] & 0x0F
    number = struct.unpack(">I", digest[start:start + 4])[0] & 0x7FFFFFFF
    return str(number % 10 ** digits).zfill(digits)


def counter_at(unix_s):
    """Which 30-second slot this moment is in."""
    return int(unix_s) // STEP_S


def code_at(secret_hex, unix_s):
    """The code the box shows at this moment."""
    return hotp(bytes.fromhex(secret_hex), counter_at(unix_s))


def seconds_left(unix_s):
    """How long the code on the screen stays (1 to 30)."""
    return STEP_S - int(unix_s) % STEP_S


def tidy_code(text):
    """'123 456' -> '123456'. Raises ValueError unless it is 6 numbers."""
    code = "".join(str(text or "").split()).replace("-", "")
    if len(code) != DIGITS or not code.isdigit() or not code.isascii():
        raise ValueError(BAD_CODE)
    return code


def matching_counter(secret_hex, code, unix_s):
    """The slot this code belongs to (now, or one slot either side), or None if it is wrong."""
    key = bytes.fromhex(secret_hex)
    now = counter_at(unix_s)
    found = None
    for counter in range(now - DRIFT_STEPS, now + DRIFT_STEPS + 1):
        if hmac.compare_digest(hotp(key, counter), code) and found is None:
            found = counter  # (keep checking every slot, so a right and a wrong code take as long)
    return found


def check_code(secret_hex, typed, unix_s, used_counters=()):
    """(counter, None) if the typed code is right and unused, else (None, message)."""
    try:
        code = tidy_code(typed)
    except ValueError as err:
        return None, str(err)
    counter = matching_counter(secret_hex, code, unix_s)
    if counter is None:
        return None, WRONG_CODE
    if counter in used_counters:
        return None, CODE_USED  # each code works for one player: texting it to a friend does not help
    return counter, None

"""The box code maths for the ESP32 (MicroPython). Owner: B.

The same sums as the server's box_code.py (HOTP, RFC 4226, a new code every 30 seconds),
written with only hashlib.sha1, so it runs on MicroPython too. tests/test_box_code.py checks
that this file and the server agree, so the box and the server always show the same code.
"""

import binascii
import hashlib

STEP_S = 30
DIGITS = 6
BLOCK = 64  # SHA-1 works on 64-byte blocks
UNIX_FROM_2000 = 946684800  # MicroPython boards count seconds from 2000, not 1970


def _hmac_sha1(key, message):
    if len(key) > BLOCK:
        key = hashlib.sha1(key).digest()
    key = key + bytes(BLOCK - len(key))
    inner = hashlib.sha1(bytes(b ^ 0x36 for b in key) + message).digest()
    return hashlib.sha1(bytes(b ^ 0x5C for b in key) + inner).digest()


def hotp(key, counter):
    message = bytes((counter >> shift) & 0xFF for shift in range(56, -8, -8))  # 8 bytes, big end first
    digest = _hmac_sha1(key, message)
    start = digest[-1] & 0x0F
    number = ((digest[start] & 0x7F) << 24 | digest[start + 1] << 16
              | digest[start + 2] << 8 | digest[start + 3])
    text = str(number % 10 ** DIGITS)
    return "0" * (DIGITS - len(text)) + text


def code_at(secret_hex, unix_s):
    return hotp(binascii.unhexlify(secret_hex), int(unix_s) // STEP_S)


def seconds_left(unix_s):
    return STEP_S - int(unix_s) % STEP_S

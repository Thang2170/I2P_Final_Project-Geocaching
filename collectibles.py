"""Rules for QR collectibles (owner: A). Plain Python, no Flask, no database.

A treasure can have a collectible: a 3D trophy and a secret code. The player who hid the
treasure prints the code as a QR sticker and puts it at the spot. Whoever finds the spot
and scans it collects the trophy into their Collection (and can look at it in AR).

The trophy is either one of ours (made by voxel_models.py) or a model the player made
themselves and uploaded as a .glb file.
"""

import json
import secrets
import struct
from datetime import timezone

from voxel_models import TROPHIES

CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O or 1/I, easy to type
CODE_LENGTH = 10
MAX_MODEL_BYTES = 5 * 1024 * 1024    # 5 MB is plenty for a phone AR model
MAX_NAME_LENGTH = 40


def make_code():
    """A random code such as 'K7QX2MRT9C'. 32^10 possibilities: impossible to guess."""
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))


def clean_code(text):
    """What a player typed or the camera read -> the code, or raise ValueError.

    Accepts the bare code or the whole link printed in the QR (.../collect/CODE).
    """
    if not isinstance(text, str):
        raise ValueError("Scan or type a code")
    text = text.strip().rstrip("/")
    if "/collect/" in text:
        text = text.rsplit("/collect/", 1)[1]
    code = text.upper().replace("-", "").replace(" ", "")
    if len(code) != CODE_LENGTH or any(ch not in CODE_ALPHABET for ch in code):
        raise ValueError("That isn't a StepQuest collectible code")
    return code


def parse_trophy(value):
    """One of our built-in trophies (voxel_models.TROPHIES). Raises ValueError."""
    if value in (None, ""):
        return "trophy"
    if value not in TROPHIES:
        raise ValueError(f"trophy must be one of: {', '.join(TROPHIES)}")
    return value


def parse_name(value, default):
    if value in (None, ""):
        return default
    if not isinstance(value, str) or len(value.strip()) > MAX_NAME_LENGTH:
        raise ValueError(f"name must be text, at most {MAX_NAME_LENGTH} characters")
    return value.strip() or default


def check_glb(data):
    """Make sure an uploaded file really is a glTF 2.0 binary model (.glb). Raises ValueError.

    We read its 12-byte header and its first chunk, which must be the JSON part, instead of
    trusting the file name: anyone can rename a virus to "trophy.glb".
    """
    if not data:
        raise ValueError("The file is empty")
    if len(data) > MAX_MODEL_BYTES:
        raise ValueError(f"The model must be at most {MAX_MODEL_BYTES // (1024 * 1024)} MB")
    if len(data) < 20:
        raise ValueError("That isn't a .glb 3D model")
    magic, version, length = struct.unpack_from("<4sII", data, 0)
    if magic != b"glTF":
        raise ValueError("That isn't a .glb 3D model (export your model as glTF binary, .glb)")
    if version != 2:
        raise ValueError("Only glTF version 2 models are supported")
    if length != len(data):
        raise ValueError("The model file is broken (its length is wrong)")
    chunk_length, chunk_type = struct.unpack_from("<I4s", data, 12)
    if chunk_type != b"JSON" or 20 + chunk_length > len(data):
        raise ValueError("The model file is broken (no JSON part)")
    try:
        info = json.loads(data[20:20 + chunk_length])
    except (ValueError, UnicodeDecodeError):
        raise ValueError("The model file is broken (bad JSON part)") from None
    if not isinstance(info, dict) or "asset" not in info:
        raise ValueError("The model file is broken (no asset info)")
    return True


def can_manage(user_id, treasure_creator_id, is_admin):
    """Who may add or change a treasure's collectible: whoever hid it, or an admin.
    The built-in demo treasures (no creator) can only be set up by an admin."""
    return is_admin or (treasure_creator_id is not None and treasure_creator_id == user_id)


def utc_iso(when):
    """A time as text the browser reads correctly, e.g. "2026-11-24T06:05:00+00:00".

    WHY: SQLite forgets the time zone, so a saved UTC time comes back "naive". Without
    "+00:00" the browser would treat it as local time and show it 8 hours off in Taiwan.
    """
    if when is None:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return when.isoformat()


def still_to_find(total_collectibles, hidden_by_me, collected):
    """How many trophies you could still collect: the ones in the game, minus the ones
    you hid yourself (you can't collect those) and the ones you already have.
    Used for the empty spots on the Collection shelf."""
    return max(0, total_collectibles - hidden_by_me - collected)

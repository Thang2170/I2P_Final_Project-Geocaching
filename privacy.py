"""Your data, your choice: download everything, or delete your band data (owner: B).

Plain Python with no Flask and no database, so it is easy to test. privacy_api.py reads the
rows; these rules decide what goes in the download and what "band data" means.

Heart rate and blood oxygen are sensitive, so a player can:
- download all their data as one JSON file (every table that points at them), and
- delete their band data (readings, paired bands, safety stops) for good.
Secrets are never in a download: the password hash and the band tokens' hashes.
"""

from datetime import date, datetime, timezone

# never put these in a download, even though they are "yours"
SECRET_COLUMNS = {"users": {"password_hash"}, "health_devices": {"token_hash"}}

# "band data": what the band measured or caused. Deleting it keeps your coins and game history.
BAND_TABLES = ("health_readings", "safety_alerts", "health_devices")

DELETE_WORD = "DELETE"  # typed to confirm, so a slip of the finger can't delete it


def clean_value(value):
    """A database value -> something JSON can hold."""
    if isinstance(value, datetime):
        return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (bytes, bytearray, memoryview)):
        return f"(a file, {len(bytes(value))} bytes)"
    return value


def clean_row(table, row):
    """One row (a dict of column -> value) for the download, secrets left out."""
    hidden = SECRET_COLUMNS.get(table, set())
    return {column: clean_value(value) for column, value in row.items() if column not in hidden}


def export_document(username, tables, now):
    """The whole download: {"about", "player", "tables": {table: [rows]}}. Empty tables are left out."""
    return {
        "about": (f"Everything StepQuest keeps about {username}, downloaded {now.date().isoformat()}. "
                  "Passwords and band tokens are never included."),
        "player": username,
        "downloaded_at": clean_value(now),
        "tables": {name: rows for name, rows in sorted(tables.items()) if rows},
    }


def export_filename(username, now):
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in username)[:40] or "player"
    return f"stepquest-{safe}-{now.date().isoformat()}.json"


def deleted_text(deleted):
    """What the page says after deleting band data."""
    def n(count, word):
        return f"{count} {word}{'' if count == 1 else 's'}"
    return (f"Deleted {n(deleted['health_readings'], 'band reading')}, {n(deleted['health_devices'], 'paired band')} "
            f"and {n(deleted['safety_alerts'], 'safety stop')}. Your coins and hunts are kept.")


def confirm_problem(data):
    """Why the delete request isn't confirmed, or None."""
    if not isinstance(data, dict) or data.get("confirm") != DELETE_WORD:
        return f'Type {DELETE_WORD} to confirm: your band data will be gone for good.'
    return None

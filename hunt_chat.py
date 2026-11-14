"""Rules for a hunt's group chat (owner: B).

Plain Python with no Flask and no database, so it is easy to test.
chat_api.py uses these rules; the chat page only shows what Python sends.

Everyone in a hunt can chat, both the players and the ones waiting in line,
so the people in line can see what is going on. Leaving the hunt takes you out of the chat.
"""

MAX_MESSAGE_CHARS = 300
HISTORY_SIZE = 100     # messages shown when the chat opens
POLL_SECONDS = 4       # how often the page asks for new messages


def parse_message(data):
    """The text of a new chat message, or raise ValueError."""
    if not isinstance(data, dict):
        raise ValueError("Send it as JSON")
    text = data.get("text")
    if not isinstance(text, str) or not text.strip():
        raise ValueError("Write something first")
    text = text.strip()
    if len(text) > MAX_MESSAGE_CHARS:
        raise ValueError(f"Keep it to {MAX_MESSAGE_CHARS} characters (yours has {len(text)})")
    return text


def parse_after(value):
    """Only messages newer than this id. Empty means "the latest ones"."""
    if value is None or str(value).strip() == "":
        return 0
    try:
        after = int(value)
    except ValueError:
        raise ValueError("after must be a whole number") from None
    if after < 0:
        raise ValueError("after must be 0 or more")
    return after


def can_chat(user_id, member_ids):
    """Only people in the hunt (playing or waiting) can read and write its chat."""
    return user_id in member_ids

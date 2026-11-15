"""Rules for a hunt's group chat (owner: B).

Plain Python with no Flask and no database, so it is easy to test.
chat_api.py uses these rules; the chat page only shows what Python sends.

Only the players who are playing can chat. People waiting in line get in
when they move up, and leaving the hunt takes you out of the chat.
"""

from queue_logic import PLAYING, queue_status

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


def chat_access(user_id, member_ids, capacity):
    """Can this player use the hunt's chat? Returns (allowed, reason shown when not allowed).

    member_ids: everyone in the hunt, in the order they joined.
    """
    status = queue_status(user_id, member_ids, capacity)
    if status is None:
        return False, "Join this hunt to see its chat."
    if status["state"] != PLAYING:
        return False, (f"You are #{status['position']} in line. "
                       "The group chat opens when you move up and start playing.")
    return True, ""


def can_chat(user_id, member_ids, capacity):
    """Only players who are playing in the hunt can read and write its chat."""
    return chat_access(user_id, member_ids, capacity)[0]


def unread_count(messages, last_read_id, user_id):
    """How many messages in a hunt's chat this player hasn't seen yet.

    messages: (message id, sender id) for the hunt's messages.
    last_read_id: the newest message id they have seen (0 if they never opened the chat).
    Your own messages never count as unread.
    """
    return sum(1 for message_id, sender_id in messages
               if message_id > last_read_id and sender_id != user_id)

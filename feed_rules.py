"""Rules for the Community feed: posts, likes and comments (owner: B).

Plain Python with no Flask and no database, so it is easy to test.
feed_api.py uses these rules; the browser only sends what the player typed.
"""

from datetime import datetime, timezone

MAX_POST_CHARS = 500
MAX_COMMENT_CHARS = 300
FEED_PAGE_SIZE = 20
MAX_COMMENTS_SHOWN = 50

# How many avatar colours app.css has (.avatar--0 to .avatar--5).
AVATAR_COLOURS = 6


def _clean_text(data, field, limit):
    if not isinstance(data, dict):
        raise ValueError("Send it as JSON")
    value = data.get(field)
    if not isinstance(value, str):
        raise ValueError(f"Write something in {field}")
    text = value.strip()
    if not text:
        raise ValueError("You can't post an empty message")
    if len(text) > limit:
        raise ValueError(f"Keep it to {limit} characters (yours has {len(text)})")
    return text


def parse_post(data):
    """The text of a new post, or raise ValueError."""
    return _clean_text(data, "text", MAX_POST_CHARS)


def parse_comment(data):
    """The text of a new comment, or raise ValueError."""
    return _clean_text(data, "text", MAX_COMMENT_CHARS)


def parse_reply(data):
    """The text of a reply to a comment, or raise ValueError. Same limits as a comment."""
    return _clean_text(data, "text", MAX_COMMENT_CHARS)


def reply_start(username):
    """What the reply box starts with when you reply to a reply: "@bob ".

    Replies are one level deep (like Facebook): replying to a reply adds to the same comment,
    and the @name shows who you are answering.
    """
    return f"@{username} "


def parse_offset(value):
    """Where the next page of the feed starts. Empty means the top."""
    if value is None or str(value).strip() == "":
        return 0
    try:
        offset = int(value)
    except ValueError:
        raise ValueError("offset must be a whole number") from None
    if offset < 0:
        raise ValueError("offset must be 0 or more")
    return offset


def avatar(username):
    """The letter and colour number of a player's picture. Same name, same colour, every time."""
    letter = username[:1].upper() if username else "?"
    colour = sum(ord(ch) for ch in username) % AVATAR_COLOURS
    return {"letter": letter, "colour": colour}


def _as_utc(moment):
    # SQLite gives back times without a time zone; they were saved in UTC.
    return moment.replace(tzinfo=timezone.utc) if moment.tzinfo is None else moment


def time_ago(then, now=None):
    """'Just now', '5 min', '3 h', '2 d', or a date like '14 Nov' for older posts."""
    now = _as_utc(now or datetime.now(timezone.utc))
    seconds = (now - _as_utc(then)).total_seconds()
    if seconds < 60:
        return "Just now"
    if seconds < 3600:
        return f"{int(seconds // 60)} min"
    if seconds < 86_400:
        return f"{int(seconds // 3600)} h"
    if seconds < 7 * 86_400:
        return f"{int(seconds // 86_400)} d"
    then = _as_utc(then)
    return f"{then.day} {then.strftime('%b')}"


def like_summary(names, liked_by_me):
    """A short line under a post, e.g. 'Liked by you and 2 others', 'Liked by ben'.

    names: usernames of the other players who liked it (not you), newest first.
    B: it starts with "Liked by", so a lone name under a post never looks like a stray word.
    """
    if liked_by_me:
        if not names:
            return "Liked by you"
        if len(names) == 1:
            return f"Liked by you and {names[0]}"
        return f"Liked by you and {len(names)} others"
    if not names:
        return ""
    if len(names) == 1:
        return f"Liked by {names[0]}"
    if len(names) == 2:
        return f"Liked by {names[0]} and {names[1]}"
    return f"Liked by {names[0]} and {len(names) - 1} others"

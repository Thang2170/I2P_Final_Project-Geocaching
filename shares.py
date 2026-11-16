"""Rules for sharing a post on the Community feed (owner: B).

Plain Python with no Flask and no database, so it is easy to test.
A share is a post of its own (so it can be liked, commented on and deleted like any post),
linked to the post it shares by a PostShare row. feed_api.py uses these rules.
"""

from feed_rules import MAX_POST_CHARS


def parse_share(data):
    """The words you add when sharing. Optional, so "" is fine."""
    if data is None:
        return ""
    if not isinstance(data, dict):
        raise ValueError("Send it as JSON")
    value = data.get("text", "")
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError("text must be words")
    text = value.strip()
    if len(text) > MAX_POST_CHARS:
        raise ValueError(f"Keep it to {MAX_POST_CHARS} characters (yours has {len(text)})")
    return text


def share_target(post_id, is_share, original_id):
    """Which post a new share points at.

    is_share: post_id is itself a share; original_id: the post it shares (None once deleted).
    Sharing a share shares the original, like Facebook, so the feed never shows a share of a
    share of a share.
    """
    if not is_share:
        return post_id
    if original_id is None:
        raise ValueError("The original post was deleted, so it can't be shared.")
    return original_id

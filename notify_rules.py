"""Rules for notifications: the bell in the top bar (owner: B).

Plain Python with no Flask and no database, so it is easy to test.
notify_api.py saves a notification when something happens and uses these rules to show it.
"""

from urllib.parse import quote

from queue_logic import PLAYING, queue_status

LIKE = "like"            # someone liked your post
COMMENT = "comment"      # someone commented on your post
MOVED_UP = "moved_up"    # you moved up from a hunt's waiting line and can play now
FRIEND_REQUEST = "friend_request"    # someone wants to be your friend (the bell shows Accept / Decline)
FRIEND_ACCEPTED = "friend_accepted"  # someone said yes to your friend request
SHARE = "share"          # someone shared your post
REPLY = "reply"          # someone replied to your comment
HUNT_WON = "hunt_won"    # A: someone won a hunt race you were in
STREAK_RISK = "streak_risk"  # B: your streak ends at midnight (habits.py writes the words)
KINDS = (LIKE, COMMENT, MOVED_UP, FRIEND_REQUEST, FRIEND_ACCEPTED, SHARE, REPLY, HUNT_WON, STREAK_RISK)

SHOWN = 20  # how many notifications the bell lists


def should_notify(actor_id, recipient_id):
    """Nobody gets a notification about their own actions (liking your own post, ...)."""
    return recipient_id is not None and actor_id != recipient_id


def message(kind, actor_name, subject):
    """What the notification says.

    actor_name: who did it (None for MOVED_UP). subject: a few words about what it was about
    (the start of the post, or the hunt's name).
    """
    if kind == LIKE:
        return f'{actor_name} liked your post "{subject}"'
    if kind == COMMENT:
        return f'{actor_name} commented on your post "{subject}"'
    if kind == MOVED_UP:
        return f'You moved up in "{subject}": you can play now, and the group chat is open'
    if kind == SHARE:
        return f'{actor_name} shared your post "{subject}"'
    if kind == REPLY:
        return f'{actor_name} replied to your comment on "{subject}"'
    if kind == FRIEND_REQUEST:
        return f"{actor_name} wants to be your friend"
    if kind == FRIEND_ACCEPTED:
        return f"{actor_name} accepted your friend request"
    if kind == HUNT_WON:
        return f'{actor_name} won the hunt "{subject}"'
    if kind == STREAK_RISK:
        return subject  # the whole sentence, from habits.streak_risk_text
    raise ValueError(f"Unknown notification kind: {kind}")


def link(kind, post_id=None, hunt_id=None, actor_name=None):
    """Where tapping the notification takes you."""
    if kind in (LIKE, COMMENT, SHARE, REPLY):
        # B: straight to that post on its own page (the feed if the post isn't known)
        return f"/posts/{post_id}" if post_id is not None else "/community"
    if kind == MOVED_UP:
        return f"/hunts/{hunt_id}/chat"
    if kind in (FRIEND_REQUEST, FRIEND_ACCEPTED):
        return f"/players/{quote(actor_name or '')}"
    if kind == HUNT_WON:
        return "/hunts"
    if kind == STREAK_RISK:
        return "/welcome"  # the home page: your ring and streak
    raise ValueError(f"Unknown notification kind: {kind}")


def short(text, limit=40):
    """The start of a post, for the notification ("Found the pond treasure, it was…")."""
    text = " ".join(text.split())  # one line
    return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"


def moved_up(before_ids, after_ids, capacity):
    """Who was waiting in line before and is playing now (after someone left).

    before_ids / after_ids: the hunt's members in the order they joined, before and after.
    """
    risen = []
    for user_id in after_ids:
        was = queue_status(user_id, before_ids, capacity)
        now = queue_status(user_id, after_ids, capacity)
        if was is not None and was["state"] != PLAYING and now["state"] == PLAYING:
            risen.append(user_id)
    return risen

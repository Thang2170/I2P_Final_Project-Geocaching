"""Rules for friends (owner: B). Both players must agree, like Facebook.

Plain Python with no Flask and no database, so it is easy to test.
friends_api.py stores one row per pair of players: (requester, addressee, status).
"""

PENDING = "pending"      # asked, not answered yet
ACCEPTED = "accepted"    # friends

# How two players are linked, as seen by "me". The profile button depends on it.
NONE = "none"            # strangers: "Add friend"
SENT = "sent"            # I asked, they haven't answered: "Request sent" (tap to cancel)
RECEIVED = "received"    # they asked me: "Accept" / "Decline"
FRIENDS = "friends"      # "Friends" (tap to unfriend)
SELF = "self"            # my own profile: no button

FRIENDS_SHOWN = 12       # how many friends the profile lists


def relation(me_id, other_id, row):
    """me and other's link. row is (requester_id, addressee_id, status) for this pair, or None."""
    if me_id == other_id:
        return SELF
    if row is None:
        return NONE
    requester_id, _addressee_id, status = row
    if status == ACCEPTED:
        return FRIENDS
    return SENT if requester_id == me_id else RECEIVED


def request_action(me_id, other_id, row):
    """What "Add friend" does: "create" a request, or "accept" theirs (you both asked).

    Raises ValueError with a message the player can read when there is nothing to do.
    """
    state = relation(me_id, other_id, row)
    if state == SELF:
        raise ValueError("You can't add yourself as a friend.")
    if state == FRIENDS:
        raise ValueError("You are already friends.")
    if state == SENT:
        raise ValueError("You already asked. Wait for an answer.")
    return "accept" if state == RECEIVED else "create"


def check_answer(me_id, other_id, row):
    """Accept or Decline needs a request from them that is still waiting."""
    if relation(me_id, other_id, row) != RECEIVED:
        raise ValueError("There is no friend request from this player.")


def check_remove(me_id, other_id, row):
    """Unfriend, or take back a request you sent."""
    if relation(me_id, other_id, row) not in (FRIENDS, SENT):
        raise ValueError("You are not friends with this player.")


def friend_ids(me_id, rows):
    """The ids of my friends, from (requester_id, addressee_id, status) rows that include me."""
    out = []
    for requester_id, addressee_id, status in rows:
        if status != ACCEPTED or me_id not in (requester_id, addressee_id):
            continue
        out.append(addressee_id if requester_id == me_id else requester_id)
    return out


def parse_feed_filter(value):
    """?only= on the feed: everyone (default) or only friends (and me)."""
    value = (value or "everyone").strip().lower()
    if value not in ("everyone", "friends"):
        raise ValueError('only must be "everyone" or "friends"')
    return value

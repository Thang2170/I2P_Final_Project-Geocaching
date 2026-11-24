"""The shop's items and rules (Feature 9, owner: B).

Plain Python with no Flask and no database, so it is easy to test.
These are demo items. Later the vouchers could work with real local shops.
"""

import secrets
from typing import NamedTuple

# Letters and digits that are hard to mix up when someone reads a code aloud
# (no 0/O or 1/I).
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 6

# Why a purchase can be refused. shop_api.py turns each code into a message.
UNKNOWN_ITEM = "unknown"
ALREADY_OWNED = "owned"
NOT_ENOUGH_COINS = "poor"


class Item(NamedTuple):
    id: str
    name: str
    description: str
    price: int          # in coins
    kind: str           # "voucher" gives a code; "item" is something you keep
    once: bool          # True: a player can own it only once


ITEMS = (
    Item("bubble-tea", "Free bubble tea", "Demo voucher for one bubble tea near campus.", 50, "voucher", False),
    Item("cafe-10", "10% off at a campus cafe", "Demo voucher. Show the code at the counter.", 30, "voucher", False),
    Item("explorer-badge", "Explorer badge",
         "An Explorer label next to your name on your profile and in the Community feed.", 20, "item", True),
    Item("gold-pin", "Gold pin", "Your own marker on the map turns gold.", 40, "item", True),
)

# A: what the "item" kinds actually do once you own them
BADGE = "explorer-badge"
GOLD_PIN = "gold-pin"


def find_item(item_id):
    """Return the Item with this id, or None."""
    for item in ITEMS:
        if item.id == item_id:
            return item
    return None


def item_to_dict(item):
    return {"id": item.id, "name": item.name, "description": item.description,
            "price": item.price, "kind": item.kind, "once": item.once}


def purchase_problem(item, balance, owns_one):
    """Return the reason a purchase must be refused, or None if it is allowed.

    item: an Item, or None if the id was not in the shop
    balance: how many coins the player has
    owns_one: True if the player already bought this item
    """
    if item is None:
        return UNKNOWN_ITEM
    if item.once and owns_one:
        return ALREADY_OWNED
    if balance < item.price:
        return NOT_ENOUGH_COINS
    return None


def perks(owned_item_ids):
    """A: what a player's items change in the app. owned_item_ids: the ids they bought."""
    owned = set(owned_item_ids)
    return {"badge": BADGE in owned, "gold_pin": GOLD_PIN in owned}


def make_voucher_code():
    """A random voucher code such as 'TH-7KQ2MX'."""
    return "TH-" + "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))

"""Verified treasures (owner: A): an admin checks a treasure is real, so trolls can't flood the map.

Every treasure still shows on the map and players can still walk to it. A verified one
gets a check mark; an unchecked one says "not verified yet".

The check is saved in its own small table (treasure_checks) instead of a new column on
"treasures": db.create_all() adds a new table to an existing geohunt.db, but never adds
columns to an old table, so nobody has to delete their database.
"""

from datetime import datetime, timezone

from models import Treasure, db


class TreasureCheck(db.Model):
    """An admin said this treasure is real. No row = not verified yet."""

    __tablename__ = "treasure_checks"
    treasure_id = db.Column(db.Integer, db.ForeignKey("treasures.id"), primary_key=True)
    verified_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    verified_at = db.Column(db.DateTime, nullable=False)


def is_verified(created_by, has_check):
    """The rule. Built-in demo treasures (no creator) count as verified; a player's
    treasure is verified once an admin checked it."""
    return created_by is None or has_check


def verified_ids():
    """The ids of every verified treasure, read in two small queries (not one per treasure)."""
    checked = set(db.session.execute(db.select(TreasureCheck.treasure_id)).scalars().all())
    rows = db.session.execute(db.select(Treasure.id, Treasure.created_by)).all()
    return {tid for tid, creator in rows if is_verified(creator, tid in checked)}


def set_verified(treasure_id, admin_id, verified):
    """Mark a treasure as checked (verified=True) or take the check back (False).

    Returns False if there is no such treasure. The caller commits.
    """
    if db.session.get(Treasure, treasure_id) is None:
        return False
    check = db.session.get(TreasureCheck, treasure_id)
    if verified and check is None:
        db.session.add(TreasureCheck(treasure_id=treasure_id, verified_by=admin_id,
                                     verified_at=datetime.now(timezone.utc)))
    elif not verified and check is not None:
        db.session.delete(check)
    return True

"""Save the demo story into the database (owner: B).

Safe to run again and again: it only adds what is missing and never changes or deletes anything.
What gets saved is listed in demo_content.py.
"""

from demo_content import (DEMO_FULL_HUNT, DEMO_PASSWORD, DEMO_TREASURES, DEMO_USERS, GIFT_REASON,
                          TREASURE_CREATOR)
from models import CoinTransaction, Hunt, HuntMember, Profile, Treasure, User, db


def _get_user(username):
    return db.session.execute(db.select(User).where(User.username == username)).scalar_one_or_none()


def seed_demo_story():
    """Add the demo users, treasures and hunt that are missing. Returns what was added."""
    added = {"users": [], "treasures": [], "hunts": []}

    for spec in DEMO_USERS:
        if _get_user(spec["username"]) is not None:
            continue
        user = User(username=spec["username"])
        user.set_password(DEMO_PASSWORD)
        db.session.add(user)
        db.session.flush()  # gives the new user an id
        db.session.add(Profile(user_id=user.id, weight_kg=spec["weight_kg"]))
        if spec["coins"]:
            db.session.add(CoinTransaction(user_id=user.id, amount=spec["coins"], reason=GIFT_REASON))
        added["users"].append(user.username)

    creator = _get_user(TREASURE_CREATOR)
    for spec in DEMO_TREASURES:
        exists = db.session.execute(db.select(Treasure.id).where(Treasure.name == spec["name"])).first()
        if exists is None:
            db.session.add(Treasure(created_by=creator.id if creator else None, **spec))
            added["treasures"].append(spec["name"])

    hunt_name = DEMO_FULL_HUNT["name"]
    if db.session.execute(db.select(Hunt.id).where(Hunt.name == hunt_name)).first() is None:
        hunt = Hunt(name=hunt_name, description=DEMO_FULL_HUNT["description"],
                    capacity=DEMO_FULL_HUNT["capacity"])
        db.session.add(hunt)
        db.session.flush()
        for username in DEMO_FULL_HUNT["members"]:
            member = _get_user(username)
            if member is not None:
                db.session.add(HuntMember(hunt_id=hunt.id, user_id=member.id))
        added["hunts"].append(hunt_name)

    db.session.commit()
    return added

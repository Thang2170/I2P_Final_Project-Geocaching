"""Reset the demo to the start of the story, so every rehearsal begins the same (owner: B).

reset_demo() deletes the demo players (demo_content.DEMO_USERS, plus any extra player names you
give it, such as the player you register on stage) and EVERYTHING that points at them: coins,
hunts, journeys and trails, posts (and other players' likes on them), bonuses, band readings,
treasures they hid (and finds of those), and so on. Then the demo story is seeded again.

It follows the database's own links (foreign keys), so tables added later are covered too.
Two links are cleared instead of deleted, so other players' things are never lost because a
demo player touched them: who won a hunt game, and which admin verified a treasure.

Other players and the built-in treasure are kept. Works while the app is running.
"""

from sqlalchemy import delete, select, update

from demo_content import DEMO_FULL_HUNT, DEMO_USERS
from demo_data import seed_demo_story
from demo_extras import DEMO_RACE, DEMO_WALKERS
from models import Hunt, User, db

KEEP_AND_CLEAR = {"winner_id", "verified_by"}  # links set to empty instead of deleting the row


def demo_usernames(extra=()):
    return [u["username"] for u in DEMO_USERS] + list(DEMO_WALKERS) + [name for name in extra if name]


def wipe_players(user_ids, hunt_ids=()):
    """Delete these players (and these hunts) and everything that points at them.

    Returns {table: rows deleted}.
    """
    tables = {t.name: t for t in db.metadata.sorted_tables}
    gone = {"users": set(user_ids), "hunts": set(hunt_ids)}  # table -> ids deleted (others may point at)
    if hunt_ids:
        db.session.execute(delete(tables["hunts"]).where(tables["hunts"].c.id.in_(hunt_ids)))
    counts = {"hunts": len(hunt_ids)} if hunt_ids else {}
    changed = True
    while changed:
        changed = False
        for table in db.metadata.sorted_tables:
            if table.name == "users":
                continue
            pk = list(table.primary_key.columns)
            for column in table.columns:
                for fk in column.foreign_keys:
                    target = fk.column.table.name
                    ids = gone.get(target)
                    if not ids:
                        continue
                    if column.name in KEEP_AND_CLEAR:
                        db.session.execute(update(table).where(column.in_(ids)).values({column.name: None}))
                        continue
                    hit = set(db.session.execute(select(pk[0]).where(column.in_(ids))).scalars())
                    new = hit - gone.get(table.name, set())
                    if not hit:
                        continue
                    db.session.execute(delete(table).where(column.in_(ids)))
                    if new:
                        gone.setdefault(table.name, set()).update(new)
                        counts[table.name] = counts.get(table.name, 0) + len(new)
                        changed = True
    db.session.execute(delete(tables["users"]).where(tables["users"].c.id.in_(user_ids)))
    counts["users"] = len(user_ids)
    return counts


def reset_demo(extra_usernames=()):
    """Delete the demo players (and these extra ones), then seed the demo story again.

    Returns {"removed": [usernames], "deleted": {table: rows}, "added": what the seed added}.
    """
    names = demo_usernames(extra_usernames)
    users = db.session.execute(select(User.id, User.username).where(User.username.in_(names))).all()
    # the full demo hunt is seeded with its members only when it is missing, so it goes too
    hunts = list(db.session.execute(select(Hunt.id).where(
        Hunt.name.in_([DEMO_FULL_HUNT["name"], DEMO_RACE["name"]]))).scalars())  # B: and the demo race
    deleted = wipe_players([uid for uid, _ in users], hunts)
    db.session.commit()
    # The rows were deleted straight in the database, so forget any objects the session still
    # remembers for them: the seed may reuse their ids (SQLAlchemy would warn about the clash).
    db.session.expunge_all()
    added = seed_demo_story()
    return {"removed": [name for _, name in users], "deleted": deleted, "added": added}

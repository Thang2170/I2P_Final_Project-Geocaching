"""Demo data for the six new ways to play (owner: B).

demo_extras.seed_demo_extras() calls seed_demo_play() at the end, so `python seed_demo.py` and
`python reset_demo.py` load it too. Safe to run again: it only adds what is missing.

- a traveler, the Golden Duck: alice released it at Pond bench and ben carried it to Cafe corner.
  It wants to reach Library steps, so demo_player can finish its journey on stage (+25 coins).
- a team treasure, "Twin benches" (2 players): log in as demo_player on one phone and alice
  on another, and both tap "I'm here" within a minute.
- a box treasure, "Gate box". Its secret is made at random here; `python simulate_box.py`
  reads it from the database and shows the codes, so no secret is ever written in the code.
- the ghost race needs nothing new: ben's demo race (demo_extras.DEMO_RACE) is the ghost.
"""

from datetime import timedelta

from box_code import new_secret
from demo_content import TREASURE_CREATOR
from models import Traveler, TravelerMove, Treasure, TreasureBox, TeamLock, User, db
from travelers import DROP, PICK, RELEASE

DEMO_TRAVELER = {"name": "The Golden Duck", "goal": "Library steps",
                 "moves": ((RELEASE, "alice", "Pond bench", 3), (PICK, "ben", "Pond bench", 2),
                           (DROP, "ben", "Cafe corner", 2))}  # (action, who, where, days ago)
TEAM_TREASURE = {"name": "Twin benches", "description": "Demo team treasure: it opens only for 2 players together.",
                 "lat": 24.7948, "lon": 120.9953, "need": 2}
BOX_TREASURE = {"name": "Gate box", "description": "Demo box treasure: type the code shown on the box.",
                "lat": 24.7956, "lon": 120.9963}


def _user(name):
    return db.session.execute(db.select(User).filter_by(username=name)).scalar_one_or_none()


def _treasure(name):
    return db.session.execute(db.select(Treasure).filter_by(name=name)).scalar_one_or_none()


def _hidden_treasure(spec, creator):
    treasure = _treasure(spec["name"])
    if treasure is None:
        treasure = Treasure(name=spec["name"], description=spec["description"], lat=spec["lat"], lon=spec["lon"],
                            created_by=creator.id)
        db.session.add(treasure)
        db.session.flush()
    return treasure


def _seed_traveler(now):
    if db.session.execute(db.select(Traveler.id).filter_by(name=DEMO_TRAVELER["name"])).first():
        return []
    goal = _treasure(DEMO_TRAVELER["goal"])
    moves = [(action, _user(who), _treasure(where), days) for action, who, where, days in DEMO_TRAVELER["moves"]]
    if goal is None or any(user is None or place is None for _, user, place, _ in moves):
        return []
    traveler = Traveler(name=DEMO_TRAVELER["name"], goal_treasure_id=goal.id, created_by=moves[0][1].id,
                        created_at=now - timedelta(days=moves[0][3]))
    db.session.add(traveler)
    db.session.flush()
    for i, (action, user, place, days) in enumerate(moves):
        db.session.add(TravelerMove(traveler_id=traveler.id, action=action, user_id=user.id, treasure_id=place.id,
                                    at=now - timedelta(days=days) + timedelta(minutes=i)))
    return [f"traveler {traveler.name}"]


def seed_demo_play(now):
    """Add what is missing. `now` is a naive UTC datetime. Returns what was added."""
    creator = _user(TREASURE_CREATOR)
    if creator is None:
        return []
    added = _seed_traveler(now)
    team = _hidden_treasure(TEAM_TREASURE, creator)
    if not db.session.execute(db.select(TeamLock.id).filter_by(treasure_id=team.id)).first():
        db.session.add(TeamLock(treasure_id=team.id, need=TEAM_TREASURE["need"], created_by=creator.id))
        added.append(f"team treasure {team.name}")
    box = _hidden_treasure(BOX_TREASURE, creator)
    if not db.session.execute(db.select(TreasureBox.id).filter_by(treasure_id=box.id)).first():
        db.session.add(TreasureBox(treasure_id=box.id, secret=new_secret(), created_by=creator.id))
        added.append(f"box treasure {box.name}")
    return added

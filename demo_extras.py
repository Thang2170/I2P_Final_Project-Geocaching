"""Demo data for the newer features: heat map walkers, a race to replay, rain and night treasures (owner: B).

demo_data.seed_demo_story() calls seed_demo_extras() at the end, so `python seed_demo.py` and
`python reset_demo.py` load it too. Safe to run again: it only adds what is missing.
demo_reset.py deletes the walkers (DEMO_WALKERS) and the race hunt (DEMO_RACE) like the other demo players.

All times are counted back from now, so the heat map's "last 30 days" and the replay always have data.
"""

import math
from datetime import datetime, timedelta, timezone

from conditions import NIGHT, RAIN
from demo_content import BUILT_IN_TREASURE_NAME, DEMO_PASSWORD, TREASURE_CREATOR
from location import haversine_m
from models import CoinTransaction, HeatVisit, Hunt, HuntMember, RacePoint, Treasure, TreasureCondition, User, db
from streaks import local_day
from territory import hex_of

# Extra demo accounts that only walk (so 5+ different players reach the same spots on the heat map).
DEMO_WALKERS = ("carol", "dan", "emma", "fei", "gao", "hana", "ivan", "jun")

# Heat map paths: (waypoints, who walked it, how many days ago). Each path is walked once by each.
# The first one is busy (everyone), the last one only by two players: it stays hidden (privacy).
GATE = (24.7955, 120.9965)
BUILT_IN = (24.795324, 120.994796)
DEMO_HEAT_PATHS = (
    ((GATE, BUILT_IN), ("alice", "ben", "demo_player") + DEMO_WALKERS, 3),
    ((BUILT_IN, (24.795924, 120.994796)), ("alice", "ben") + DEMO_WALKERS[:7], 5),
    ((BUILT_IN, (24.794924, 120.994296)), ("ben",) + DEMO_WALKERS[:5], 8),
    ((GATE, (24.7968, 120.9975)), DEMO_WALKERS[2:8], 12),
    (((24.7968, 120.9975), (24.7978, 120.9990)), ("carol", "dan"), 2),
)
STEP_M = 15  # a point every 15 m along each path, so no hexagon is skipped

# A finished hunt race to replay. Each player walks from their start towards the treasure;
# the winner arrives at the finish, the others are part of the way there.
DEMO_RACE = {
    "name": "Pond sprint (demo)",
    "description": "Demo race that already finished. Open it to watch the replay.",
    "capacity": 4,
    "treasure": BUILT_IN_TREASURE_NAME,
    "days_ago": 2,
    "duration_s": 150,
    "winner": "ben",
    # player, start point, how far along the way they get by the finish (1.0 = at the treasure)
    "players": (("ben", (24.7962, 120.9958), 1.0),
                ("alice", (24.7944, 120.9960), 0.8),
                ("demo_player", (24.7955, 120.9935), 0.65)),
}
RACE_POINT_EVERY_S = 5

# Rain and night treasures, hidden by alice (at least 10 m from every other treasure).
DEMO_CONDITION_TREASURES = (
    {"name": "Moon gate", "description": "Demo night treasure: only out after dark.",
     "lat": 24.7949, "lon": 120.9958, "condition": NIGHT},
    {"name": "Puddle stone", "description": "Demo rain treasure: only out in the rain.",
     "lat": 24.7961, "lon": 120.9951, "condition": RAIN},
)


def _user(name):
    return db.session.execute(db.select(User).where(User.username == name)).scalar_one_or_none()


def _points_along(waypoints, step_m=STEP_M):
    """Points every step_m along straight lines between the waypoints."""
    out = []
    for (lat1, lon1), (lat2, lon2) in zip(waypoints, waypoints[1:]):
        n = max(1, int(haversine_m(lat1, lon1, lat2, lon2) // step_m))
        out += [(lat1 + (lat2 - lat1) * i / n, lon1 + (lon2 - lon1) * i / n) for i in range(n + 1)]
    return out


def _seed_walkers():
    added = []
    for name in DEMO_WALKERS:
        if _user(name) is None:
            user = User(username=name)
            user.set_password(DEMO_PASSWORD)
            db.session.add(user)
            added.append(name)
    db.session.flush()
    return added


def _seed_heat(now):
    added = 0
    for waypoints, walkers, days_ago in DEMO_HEAT_PATHS:
        day = local_day(now - timedelta(days=days_ago))
        cells = {hex_of(lat, lon) for lat, lon in _points_along(waypoints)}
        for name in walkers:
            user = _user(name)
            if user is None:
                continue
            for q, r in cells:
                exists = db.session.execute(db.select(HeatVisit.id).where(
                    HeatVisit.user_id == user.id, HeatVisit.day == day, HeatVisit.q == q, HeatVisit.r == r)).first()
                if not exists:
                    db.session.add(HeatVisit(user_id=user.id, q=q, r=r, day=day))
                    added += 1
    return added


def _seed_race(now):
    from hunt_game_api import HuntGame  # here: hunt_game_api imports a lot of the app
    if db.session.execute(db.select(Hunt.id).where(Hunt.name == DEMO_RACE["name"])).first():
        return []
    treasure = db.session.execute(db.select(Treasure).where(Treasure.name == DEMO_RACE["treasure"])).scalar()
    players = [(_user(name), start, reach) for name, start, reach in DEMO_RACE["players"]]
    if treasure is None or any(user is None for user, _, _ in players):
        return []
    started = (now - timedelta(days=DEMO_RACE["days_ago"])).replace(tzinfo=None)
    finished = started + timedelta(seconds=DEMO_RACE["duration_s"])
    hunt = Hunt(name=DEMO_RACE["name"], description=DEMO_RACE["description"], capacity=DEMO_RACE["capacity"],
                created_at=started - timedelta(minutes=10))
    db.session.add(hunt)
    db.session.flush()
    for user, _, _ in players:
        db.session.add(HuntMember(hunt_id=hunt.id, user_id=user.id, joined_at=started - timedelta(minutes=5)))
    winner = _user(DEMO_RACE["winner"])
    db.session.add(HuntGame(hunt_id=hunt.id, treasure_id=treasure.id, started_at=started,
                            winner_id=winner.id, finished_at=finished))
    from hunt_game import WIN_BONUS, WIN_REASON  # the winner got the race bonus, like a real win
    db.session.add(CoinTransaction(user_id=winner.id, amount=WIN_BONUS, reason=WIN_REASON, created_at=finished))
    steps = DEMO_RACE["duration_s"] // RACE_POINT_EVERY_S
    for user, (lat, lon), reach in players:
        for i in range(steps):  # the winner's last point (on the treasure) is added by the replay
            k = reach * i / steps
            bend = 0.00012 * math.sin(math.pi * k / max(reach, 0.01))  # a gentle curve, not a ruler line
            db.session.add(RacePoint(hunt_id=hunt.id, user_id=user.id,
                                     lat=lat + (treasure.lat - lat) * k + bend,
                                     lon=lon + (treasure.lon - lon) * k - bend,
                                     at=started + timedelta(seconds=i * RACE_POINT_EVERY_S)))
    return [DEMO_RACE["name"]]


def _seed_conditions():
    creator = _user(TREASURE_CREATOR)
    if creator is None:
        return []
    added = []
    for spec in DEMO_CONDITION_TREASURES:
        if db.session.execute(db.select(Treasure.id).where(Treasure.name == spec["name"])).first():
            continue
        treasure = Treasure(name=spec["name"], description=spec["description"], lat=spec["lat"], lon=spec["lon"],
                            created_by=creator.id)
        db.session.add(treasure)
        db.session.flush()
        db.session.add(TreasureCondition(treasure_id=treasure.id, condition=spec["condition"]))
        added.append(spec["name"])
    return added


def seed_demo_extras(now=None):
    """Add what is missing. Returns a list of what was added (for seed_demo.py's printout)."""
    now = now or datetime.now(timezone.utc)
    added = [f"walker {name}" for name in _seed_walkers()]
    added += [f"race {name}" for name in _seed_race(now)]
    added += [f"treasure {name}" for name in _seed_conditions()]
    visits = _seed_heat(now)
    if visits:
        added.append(f"{visits} heat map visits")
    db.session.commit()
    return added

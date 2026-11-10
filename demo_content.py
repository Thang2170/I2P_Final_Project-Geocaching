"""What the demo database contains (owner: B).

Plain Python with no Flask and no database, so it is easy to test and easy to edit.
demo_data.py saves all of this; run `python seed_demo.py` to load it.
"""

# Every demo account uses this password. It is for rehearsals only: never use it on a real server.
DEMO_PASSWORD = "demo1234"

# username, weight in kg, starting coins (a gift, so the shop can be shown straight away)
DEMO_USERS = (
    {"username": "demo_player", "weight_kg": 60, "coins": 60},   # the account to log in with
    {"username": "alice", "weight_kg": 55, "coins": 0},          # hid the extra treasures
    {"username": "ben", "weight_kg": 70, "coins": 0},            # fills the demo hunt
)

# Hidden by alice. Placed 40 to 120 m from the built-in demo treasure (24.795324, 120.994796),
# and always at least 10 m from each other. To put one on a real campus spot, change its numbers.
DEMO_TREASURES = (
    {"name": "Pond bench", "description": "Demo treasure by the water.", "lat": 24.795324, "lon": 120.995796},
    {"name": "Library steps", "description": "Demo treasure near the stairs.", "lat": 24.795924, "lon": 120.994796},
    {"name": "Cafe corner", "description": "Demo treasure at the corner.", "lat": 24.794924, "lon": 120.994296},
)
TREASURE_CREATOR = "alice"

# A hunt that is already full, so joining it shows the waiting line.
# members are listed in join order: they take the places.
DEMO_FULL_HUNT = {
    "name": "Full house (demo)",
    "description": "Demo hunt with no free place. Join to see the waiting line.",
    "capacity": 2,
    "members": ("alice", "ben"),
}

# Why the starting coins exist in the ledger.
GIFT_REASON = "demo_gift"

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

# The treasure saved by models.seed_demo_data (test_demo_data checks the two stay equal).
BUILT_IN_TREASURE_NAME = "National Tsing Hua University"

# Finished hunts, so the Community page is not empty. Nobody hunts their own treasure:
# alice hid the three extra ones, so ben reaches those, and alice reaches the built-in one.
DEMO_JOURNEYS = (
    {"username": "ben", "treasure": "Pond bench", "distance_m": 180, "duration_s": 250},
    {"username": "ben", "treasure": "Library steps", "distance_m": 260, "duration_s": 340},
    {"username": "alice", "treasure": BUILT_IN_TREASURE_NAME, "distance_m": 420, "duration_s": 560},
)

# Posts on the Community feed. likes: who liked it; comments: (who, what), oldest first.
DEMO_POSTS = (
    {"username": "alice",
     "text": "Just hid three new treasures around campus: by the pond, on the library steps and at the cafe corner. Good luck!",
     "likes": ("ben", "demo_player"),
     "comments": (("ben", "Found two of them already!"), ("alice", "Nice! The cafe one is the tricky one."))},
    {"username": "ben",
     "text": "Anyone up for an evening walk? The Full house hunt has a waiting line, but join anyway.",
     "likes": ("alice",),
     "comments": ()},
)

# Likes and comments on the posts that finished hunts make by themselves.
# Each is found by the player who did the hunt and the treasure's name.
DEMO_HUNT_REACTIONS = (
    {"username": "ben", "treasure": "Pond bench",
     "likes": ("alice", "demo_player"),
     "comments": (("alice", "Under five minutes, wow."),)},
)

# A hunt chat, so the group chat isn't empty on demo day. alice and ben join the everyday demo hunt
# (made by models.seed_demo_hunt, 5 places), so demo_player can still join it and read the chat.
DEMO_CHAT_HUNT = "NTHU campus walk"
DEMO_CHAT = {
    "members": ("alice", "ben"),
    "messages": (
        ("alice", "Hi! Meet at the main gate at 5?"),
        ("ben", "Sounds good. I found Pond bench already, it's right by the water."),
        ("alice", "Nice! Let's try Library steps next."),
    ),
}

# Players who have already "seen" the first-time tour, so it doesn't pop up in the middle of the demo.
# To show the tour on purpose, open /?tour.
DEMO_TOUR_SEEN = ("demo_player",)

# ---------- social (B): ratings, friends, a share and a reply ----------

# Stars (1-5) from players who walked to that treasure (see DEMO_JOURNEYS), so the welcome page
# has a Top rated row and a Trending this week row on demo day.
DEMO_RATINGS = (
    ("ben", "Pond bench", 5),
    ("ben", "Library steps", 4),
    ("alice", BUILT_IN_TREASURE_NAME, 5),
)

# alice and ben are friends. ben has asked demo_player, so the bell shows Accept / Decline.
DEMO_FRIENDS = (("alice", "ben"),)
DEMO_FRIEND_REQUESTS = (("ben", "demo_player"),)

# ben shares alice's "Just hid three new treasures" post (found by its first words).
DEMO_SHARES = (
    {"username": "ben", "post_by": "alice", "post_starts": "Just hid three new treasures",
     "text": "Go find these, they're fun!"},
)

# A reply under a comment: (who replies, whose comment, the comment's first words, the reply).
DEMO_REPLIES = (
    ("demo_player", "ben", "Found two of them already", "@ben which two? I'm still looking for all three."),
)

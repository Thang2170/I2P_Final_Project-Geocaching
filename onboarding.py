"""The first-time tour and the "first quests" checklist (owner: B).

Plain Python with no Flask and no database, so it is easy to test and easy to edit.
onboarding_api.py sends this to the map page, which only shows it.
To change what the tour says, change TOUR_STEPS below.
"""

from coins import COINS_PER_FIND
from location import FOUND_RADIUS_M

# How a player left the tour. Both mean "don't show it again by itself".
FINISHED = "finished"
SKIPPED = "skipped"
ENDINGS = (FINISHED, SKIPPED)

# One slide each. "sprite" is a picture from pixel.css (coin, chest, hero, tree, sparkle).
TOUR_STEPS = (
    {"id": "welcome", "sprite": "hero",
     "title": "Welcome to StepQuest!",
     "text": "Treasures are hidden at real places around you. Walk to them, find them and earn coins. "
             "This quick tour shows you how. It takes under a minute."},
    {"id": "map", "sprite": "chest",
     "title": "The map",
     "text": "Every chest is a hidden treasure. Tap one to see its hint, how far it is to walk "
             "and the route there. The gold coin is the treasure you are hunting now."},
    {"id": "journey", "sprite": "coin",
     "title": "Go and find it",
     "text": f"Press Start journey and walk. Your time, steps and calories count up as you go. "
             f"Get within {FOUND_RADIUS_M} m and the treasure is yours: +{COINS_PER_FIND} coins, "
             f"and your hunt is saved."},
    {"id": "hide", "sprite": "tree",
     "title": "Hide your own",
     "text": "Open Hide a treasure, tap the map where it goes, write a hint and add a photo. "
             "Other players will come looking for it."},
    {"id": "together", "sprite": "sparkle",
     "title": "Play together",
     "text": "Join a group hunt (if it is full, you wait in line), share your finds on the "
             "Community feed, and climb the Leaderboard. Spend your coins in the Shop."},
    {"id": "quests", "sprite": "coin",
     "title": "Your first quests",
     "text": "Here is where to start. Each one ticks itself off when you do it."},
)

# The checklist on the last slide: (id, what to do, where to do it).
FIRST_QUESTS = (
    ("weight", "Save your weight, so calories are right", "/login"),
    ("find", "Find your first treasure", "/"),
    ("hide", "Hide a treasure", "/upload"),
    ("post", "Say hi on the Community feed", "/community"),
    ("join", "Join a group hunt", "/hunts"),
    ("buy", "Buy something in the Shop", "/shop"),
)


def parse_ending(data):
    """How the player left the tour: "finished" or "skipped". Raises ValueError otherwise."""
    how = data.get("how") if isinstance(data, dict) else None
    if how not in ENDINGS:
        raise ValueError(f"how must be one of: {', '.join(ENDINGS)}")
    return how


def should_show(already_seen, asked_again=False):
    """Show the tour to new players, and to anyone who asks for it again (Replay the tour)."""
    return asked_again or not already_seen


def quest_list(done_ids):
    """The checklist with each quest marked done or not, plus how many are done.

    done_ids: the ids from FIRST_QUESTS that this player has already done.
    """
    quests = [{"id": qid, "text": text, "link": link, "done": qid in done_ids}
              for qid, text, link in FIRST_QUESTS]
    done = sum(q["done"] for q in quests)
    return {"items": quests, "done": done, "total": len(quests), "all_done": done == len(quests)}

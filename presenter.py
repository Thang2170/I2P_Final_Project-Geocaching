"""Presenter mode: a run sheet for the final demo that walks through the app page by page (owner: B).

Plain Python with no Flask and no database, so it is easy to test and easy to edit.
presenter_api.py keeps which step you are on (in the login session) and shows a small panel
on every page: who talks, what to say, and a Next button that opens the next page.
A presentation clicker works too: it sends Page Down / Page Up.

To change the demo, change STEPS below. Each step:
    page    where Next takes you (it may include ?fake=... for a fake position)
    who     A, B or C (who talks: see PITCH_SCRIPT.md)
    title   a few words
    say     2 or 3 short talking points (prompts, not a script to read out)
    look    a CSS selector the panel outlines on that page, or None
"""

# The two demo positions from PITCH_SCRIPT.md: near the first treasure, then standing on it.
NEAR = "24.7955,120.9965"
ON_IT = "24.795324,120.994796"

STEPS = (
    {"id": "map", "page": f"/?fake={NEAR}", "who": "A", "title": "The map and a walking route",
     "say": ("Chests are hidden treasures; the orange line is a real walking route.",
             "Distance is haversine in Python; the route comes from OpenRouteService.",
             "Tap New route for a different path."),
     "look": "#map"},
    {"id": "find", "page": f"/?fake={ON_IT}", "who": "B", "title": "Find it, earn coins",
     "say": ("Standing on the treasure: the server checks the 20 m rule, then pays.",
             "It never pays twice, and you can't find your own treasure.",
             "Couldn't find one? 'I looked, but couldn't find it': 3 reports and it's marked maybe missing."),
     "look": "#status"},
    {"id": "hide", "page": "/upload", "who": "B", "title": "Hide a treasure",
     "say": ("Tap the map, write a hint, add a photo.",
             "New: a treasure can appear only in the rain, or only after dark (real sun position).",
             "Two treasures can't be within 10 m of each other."),
     "look": "#form"},
    {"id": "hunts", "page": "/hunts", "who": "A", "title": "Group hunts and the waiting line",
     "say": ("A full hunt puts you in a waiting line; you move up when someone leaves.",
             "Start a race: the first player to reach the treasure wins +20 coins."),
     "look": "#hunts"},
    {"id": "replay", "page": "/hunts/demo-replay", "who": "B", "title": "Race replay",
     "say": ("Every racer's path is saved while the race runs.",
             "Python sets the speed so any race replays in about 20 seconds."),
     "look": "#replayMap"},
    {"id": "trails", "page": "/trails", "who": "C", "title": "Treasure Trails",
     "say": ("Pick a walk length: Python plans a loop through several treasures.",
             "Splits and personal bests, like a running app."),
     "look": None},
    {"id": "health", "page": "/report", "who": "C", "title": "Health band and weekly report",
     "say": ("The ESP32 band sends heart rate and SpO2; Python checks the zones.",
             "Each week: minutes in each heart-rate zone, compared with last week."),
     "look": None},
    {"id": "community", "page": "/community", "who": "B", "title": "Community",
     "say": ("Finished hunts post themselves; like, comment, share.",
             "Friends and notifications in the bell."),
     "look": None},
    {"id": "heatmap", "page": "/heatmap", "who": "B", "title": "Campus heat map",
     "say": ("Where people walk most, from the last 30 days.",
             "A spot shows only once 5 different players walked there, so nobody's own path shows."),
     "look": "#heatMap"},
    {"id": "access", "page": "/login", "who": "A", "title": "Step-free routes",
     "say": ("On the Account page: step-free routes for a wheelchair or a buggy.",
             "OpenRouteService's wheelchair profile: no steps, gentle slopes, low kerbs."),
     "look": "#accessBox"},
    {"id": "shop", "page": "/shop", "who": "C", "title": "Spend your coins",
     "say": ("Buy a bubble tea voucher with the coins you walked for.",
             "Too few coins: the shop says so."),
     "look": None},
)

START = "start"
NEXT = "next"
BACK = "back"
STOP = "stop"
ACTIONS = (START, NEXT, BACK, STOP)

END_PAGE = "/present?done=1"


def parse_action(data):
    """{"action": "start" | "next" | "back" | "stop"} -> the action. Raises ValueError otherwise."""
    action = data.get("action") if isinstance(data, dict) else None
    if action not in ACTIONS:
        raise ValueError(f"action must be one of: {', '.join(ACTIONS)}")
    return action


def move(current, action, total=None):
    """The step index after this action, or None when presenter mode ends.

    current: the step now (None if not presenting). Next after the last step ends it;
    Back on the first step stays there.
    """
    total = len(STEPS) if total is None else total
    if action == START:
        return 0
    if action == STOP or current is None:
        return None
    if action == NEXT:
        return current + 1 if current + 1 < total else None
    return max(0, current - 1)


def panel(index):
    """What the panel on each page shows for this step, or None if index is not a step."""
    if index is None or not 0 <= index < len(STEPS):
        return None
    step = STEPS[index]
    last = index == len(STEPS) - 1
    return {"index": index, "number": index + 1, "total": len(STEPS), "id": step["id"],
            "who": step["who"], "title": step["title"], "say": list(step["say"]),
            "look": step["look"], "page": step["page"],
            "next_label": "Finish" if last else f"Next: {STEPS[index + 1]['title']}",
            "first": index == 0, "last": last}


def page_after(index):
    """Where to go after an action: the step's page, or the end page when it is over."""
    return STEPS[index]["page"] if index is not None else END_PAGE


def run_sheet():
    """Every step, for the start page (a printable list)."""
    return [{"number": i + 1, "who": s["who"], "title": s["title"], "page": s["page"], "say": list(s["say"])}
            for i, s in enumerate(STEPS)]


def who_talks():
    """How many steps each person presents, e.g. {"A": 3, "B": 5, "C": 3}."""
    counts = {}
    for step in STEPS:
        counts[step["who"]] = counts.get(step["who"], 0) + 1
    return counts


def who_text():
    """"A presents 3 steps · B presents 5 · C presents 3", for the start page."""
    counts = who_talks()
    parts = [f"{who} presents {counts[who]} step{'s' if counts[who] != 1 else ''}" for who in sorted(counts)]
    return " · ".join(parts)

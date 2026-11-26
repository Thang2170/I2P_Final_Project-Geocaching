"""Walking modes (owner: B; C's idea #6). Plain Python with no Flask and no database.

- normal:  the usual game
- tryhard: walk fast. Keep an average pace of TRYHARD_PACE_S (10:00 per km) or quicker on a hunt
           and it pays a big bonus: TRYHARD_COINS_PER_KM, at least TRYHARD_MIN and at most TRYHARD_MAX
- calm:    a mental-health walk. The map points you to calm spots (parks and trees, water,
           quiet places) and each one gives a short mindfulness prompt instead of a riddle.
           No clock pressure: the pace is hidden, and slow, mindful hunts (5+ minutes) to a calm
           spot pay CALM_COINS

Which spots are calm is worked out from the words in a treasure's name and hint.
"""

import re
from datetime import date

MODES = {
    "normal": "Normal",
    "tryhard": "Try-hard",
    "calm": "Calm walk",
}
MODE_TEXT = {
    "normal": "The usual treasure hunt.",
    "tryhard": "Walk fast: keep 10:00 per km or quicker on a hunt for a big coin bonus.",
    "calm": "A slow walk for your head. Calm spots glow green, and each gives you a mindful moment.",
}

TRYHARD_PACE_S = 600          # seconds per km: 10:00 /km is a brisk walk (6 km/h)
TRYHARD_MIN_M = 200           # too short to count as a try-hard effort
TRYHARD_COINS_PER_KM = 20
TRYHARD_MIN, TRYHARD_MAX = 5, 40

CALM_MIN_S = 5 * 60           # a calm hunt takes its time
CALM_COINS = 5

# kind -> words that mark a calm spot (English, and Chinese for NTHU names)
CALM_WORDS = {
    "water": ("pond", "lake", "river", "stream", "fountain", "water", "creek", "湖", "池", "河", "水"),
    "green": ("park", "garden", "tree", "trees", "forest", "grass", "lawn", "flower", "flowers", "bamboo",
              "hill", "trail", "wood", "woods", "公園", "花園", "樹", "林", "草", "竹", "山"),
    "quiet": ("library", "bench", "temple", "chapel", "quiet", "courtyard", "pavilion", "rooftop",
              "圖書館", "亭", "廟", "靜"),
}
KIND_WORDS = {"water": "by the water", "green": "among the trees", "quiet": "a quiet spot"}

PROMPTS = {
    "water": (
        "Watch the water for one minute. Notice how it moves, and let your breathing slow to match it.",
        "Listen: can you hear the water? Count three sounds near you and three far away.",
        "Look at the reflections on the surface. Breathe in for 4, hold for 4, out for 6. Do it three times.",
    ),
    "green": (
        "Find one leaf or flower and look at it closely for 30 seconds: its colour, edges and lines.",
        "Stand still and feel your feet on the ground. Take five slow breaths and notice the smell of the air.",
        "Name five things you can see, four you can hear, three you can touch. Take your time.",
    ),
    "quiet": (
        "Sit or stand comfortably. Close your eyes and take ten slow breaths, counting each one out.",
        "Notice how your body feels after the walk: your legs, your shoulders, your breathing. Let your shoulders drop.",
        "Think of one small thing that went well today, and one person you are glad to know.",
    ),
}


def parse_mode(value):
    if value not in MODES:
        raise ValueError(f"mode must be one of: {', '.join(MODES)}")
    return value


# ---------------------------------------------------------------- try-hard

def pace_s_per_km(distance_m, duration_s):
    """Average pace in seconds per km, or None if you have hardly moved."""
    if distance_m < 20 or duration_s <= 0:
        return None
    return duration_s / (distance_m / 1000)


def fmt_pace(seconds_per_km):
    s = round(seconds_per_km)
    return f"{s // 60}:{s % 60:02d}"


def pace_status(distance_m, duration_s):
    """How a try-hard walk is going: {"on_pace", "pace", "target", "text"}."""
    pace = pace_s_per_km(distance_m, duration_s)
    target = fmt_pace(TRYHARD_PACE_S)
    if pace is None:
        return {"on_pace": None, "pace": None, "target": target, "text": f"Go! Target pace {target} /km."}
    on_pace = pace <= TRYHARD_PACE_S
    if on_pace:
        text = f"On pace: {fmt_pace(pace)} /km (target {target}). Keep it up!"
    else:
        text = f"Speed up: {fmt_pace(pace)} /km, the target is {target} /km."
    return {"on_pace": on_pace, "pace": fmt_pace(pace), "target": target, "text": text}


CALM_LINE = "No rush. Breathe slowly and notice what is around you."


def mode_line(mode, distance_m, duration_s):
    """The line under the journey stats: the try-hard pace, the calm reminder, or nothing (normal).

    Returns {"mode", "text", "on_pace"} (on_pace is None unless try-hard has enough to go on).
    """
    if mode == "tryhard":
        status = pace_status(distance_m, duration_s)
        return {"mode": mode, "text": status["text"], "on_pace": status["on_pace"]}
    if mode == "calm":
        return {"mode": mode, "text": CALM_LINE, "on_pace": None}
    return {"mode": "normal", "text": "", "on_pace": None}


def tryhard_bonus(distance_m, duration_s):
    """(coins, text) for a finished try-hard hunt. 0 coins if the pace was too slow."""
    if distance_m < TRYHARD_MIN_M:
        return 0, f"Try-hard hunts need at least {TRYHARD_MIN_M} m."
    pace = pace_s_per_km(distance_m, duration_s)
    if pace is None or pace > TRYHARD_PACE_S:
        return 0, f"Your pace was {fmt_pace(pace) if pace else '–'} /km: try-hard needs {fmt_pace(TRYHARD_PACE_S)}."
    coins = max(TRYHARD_MIN, min(TRYHARD_MAX, round(distance_m / 1000 * TRYHARD_COINS_PER_KM)))
    return coins, f"Try-hard: {fmt_pace(pace)} /km! +{coins} coins."


# ---------------------------------------------------------------- calm

def calm_kind(name, description=""):
    """'water', 'green' or 'quiet' if the treasure sounds like a calm spot, else None."""
    text = f"{name} {description}".lower()
    words = set(re.findall(r"[a-z]+", text))
    for kind, keys in CALM_WORDS.items():
        for key in keys:
            if (key in words) if key.isascii() else (key in text):
                return kind
    return None


def calm_prompt(kind, treasure_id, day):
    """The mindfulness prompt for this spot today: changes every day, same for everyone."""
    options = PROMPTS[kind]
    return options[(treasure_id + day.toordinal()) % len(options)]


def calm_spot(treasure_id, name, description, day=None):
    """{"kind", "where", "prompt"} for a calm spot, or None."""
    kind = calm_kind(name, description)
    if kind is None:
        return None
    return {"kind": kind, "where": KIND_WORDS[kind],
            "prompt": calm_prompt(kind, treasure_id, day or date.today())}


def calm_bonus(is_calm_spot, duration_s):
    """(coins, text) for a finished calm hunt."""
    if not is_calm_spot:
        return 0, "Calm walks pay a bonus at calm spots (green on the map)."
    if duration_s < CALM_MIN_S:
        return 0, "No rush on a calm walk: take at least 5 minutes for the bonus next time."
    return CALM_COINS, f"A mindful walk. +{CALM_COINS} coins."

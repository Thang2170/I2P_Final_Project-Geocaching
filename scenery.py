"""Random pixel landscapes for the login screen and the welcome banner (owner: A).

Every time a page is shown, Python picks one landscape (a sunny meadow, a sakura forest or a
pine forest with a waterfall) and scatters its scenery and creatures at random places. The
templates only draw what this returns (templates/_scene.html); the pictures are pixel_art.py
sprites, and their own frames make them move (the cat breathes, the trees sway).

Plain Python, no Flask: app.py makes random_scene() available to every template.
"""

import random

# The sky in four hard bands (top to bottom), the way old games faked a gradient
SCENES = {
    "meadow": {
        "sky": ("#7ccbe4", "#8fd3e8", "#a6dcec", "#bfe6ef"),
        "props": ["tree", "flowers", "rock", "flowers"],
        "creatures": ["butterfly", "dog", "bird", "butterfly"],
        "falling": "leaf",
        "landmark": None,
        "sun": True,
    },
    "sakura": {
        "sky": ("#f6c9d6", "#f9d6e0", "#fbe3ea", "#fdf0f3"),
        "props": ["sakura", "sakura", "flowers"],
        "creatures": ["cat", "butterfly", "bird"],
        "falling": "petal",
        "landmark": None,
        "sun": True,
    },
    "pines": {
        "sky": ("#5aa9c9", "#73b9d4", "#8fc9de", "#acd8e8"),
        "props": ["pine", "pine", "rock", "pine"],
        "creatures": ["bird", "dog", "cat"],
        "falling": "leaf",
        "landmark": "waterfall",
        "sun": False,
    },
}

FLYERS = {"butterfly", "bird"}   # these fly in the sky; the others stay on the grass
GROUND_TOP_PX = 96               # the grass starts this high above the bottom (pixel.css .scene__ground)
FALLING_COUNT = 6


def sky_css(colours):
    """The four sky bands as one CSS background."""
    a, b, c, d = colours
    return f"linear-gradient(to bottom, {a} 0 36%, {b} 36% 52%, {c} 52% 64%, {d} 64% 100%)"


def _spread(rng, count, low, high):
    """count positions (percent of the width) between low and high, not bunched together:
    the range is cut into equal slots and each position lands somewhere in its own slot."""
    width = (high - low) / count
    return [round(low + width * i + rng.uniform(0, width * 0.7), 1) for i in range(count)]


def pick_scene(rng=random):
    """One random landscape: {"name", "sky", "sun", "items": [...]}.

    Each item is {"sprite", "kind", "left" (% of the width), "bottom" (px), "scale", "delay" (s)}.
    kind: "prop" (scenery on the horizon), "walker" (a creature on the grass),
    "flyer" (in the sky) or "fall" (a petal or leaf drifting down).
    """
    name = rng.choice(sorted(SCENES))
    scene = SCENES[name]
    items = []

    # Scenery along the horizon, spread over the whole width
    props = [rng.choice(scene["props"]) for _ in range(rng.randint(4, 6))]
    for sprite, left in zip(props, _spread(rng, len(props), 0, 94)):
        scale = 2 if sprite in ("tree", "pine", "sakura") else 1.5  # sprites are already 3 px per pixel
        items.append({"sprite": sprite, "kind": "prop", "left": left, "bottom": GROUND_TOP_PX - 4,
                      "scale": scale, "delay": round(rng.uniform(0, 2), 2)})
    if scene["landmark"]:
        items.append({"sprite": scene["landmark"], "kind": "prop", "left": round(rng.uniform(55, 70), 1),
                      "bottom": GROUND_TOP_PX - 4, "scale": 2.5, "delay": 0})

    # Two or three creatures: flyers on the right half of the sky (the headline sits top left)
    for sprite in rng.sample(scene["creatures"], rng.randint(2, 3)):
        if sprite in FLYERS:
            items.append({"sprite": sprite, "kind": "flyer", "left": round(rng.uniform(55, 88), 1),
                          "bottom": rng.randint(170, 250), "scale": 1.5, "delay": round(rng.uniform(0, 4), 2)})
        else:
            items.append({"sprite": sprite, "kind": "walker", "left": round(rng.uniform(4, 50), 1),
                          "bottom": GROUND_TOP_PX - 30, "scale": 1.5, "delay": 0})

    # Petals or leaves drifting down, each starting at its own time
    for left in _spread(rng, FALLING_COUNT, 0, 100):
        items.append({"sprite": scene["falling"], "kind": "fall", "left": left, "bottom": 0,
                      "scale": 1, "delay": round(rng.uniform(0, 9), 2)})

    return {"name": name, "sky": sky_css(scene["sky"]), "sun": scene["sun"], "items": items}


def random_scene():
    """For the templates: a new landscape on every page view."""
    return pick_scene(random)

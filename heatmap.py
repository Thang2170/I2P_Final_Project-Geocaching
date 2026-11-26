"""Campus heat map: where people walk most (owner: B).

Plain Python with no Flask and no database, so it is easy to test.
heatmap_api.py saves which 40 m hexagon (the same grid as the territory game) each player
walked through on each day, and uses these rules to build the map. Rows older than
KEEP_DAYS are deleted.

Privacy: a hexagon only shows when at least MIN_PLAYERS different players walked
through it, so nobody's own path (their dorm, their lab) can be read off the map.
It counts players, not visits, so one person walking back and forth can't make a spot hot.
"""

from territory import hex_centre, hex_corners

MIN_PLAYERS = 5            # fewer different players than this, and the hexagon is not shown
DAY_CHOICES = (7, 30, 90)  # how far back you can look
DEFAULT_DAYS = 30
KEEP_DAYS = max(DAY_CHOICES)  # older visits are deleted

# Five shades, light to dark. A hexagon's shade is the highest level its player count reaches.
LEVELS = (5, 7, 10, 15, 25)


def parse_days(value):
    """?days= from the page. Empty means DEFAULT_DAYS. Raises ValueError otherwise."""
    if value in (None, ""):
        return DEFAULT_DAYS
    try:
        days = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"days must be one of: {', '.join(map(str, DAY_CHOICES))}") from None
    if days not in DAY_CHOICES:
        raise ValueError(f"days must be one of: {', '.join(map(str, DAY_CHOICES))}")
    return days


def level_of(players):
    """1 to 5 (0 = not shown)."""
    return sum(1 for low in LEVELS if players >= low)


def legend():
    """The legend's rows: [{"level", "label"}], lightest first."""
    rows = []
    for i, low in enumerate(LEVELS):
        high = LEVELS[i + 1] - 1 if i + 1 < len(LEVELS) else None
        rows.append({"level": i + 1, "label": f"{low}–{high} players" if high else f"{low}+ players"})
    return rows


def heat_cells(visits):
    """visits: (user_id, q, r) rows. Returns the hexagons to draw, busiest first.

    Each: {"q", "r", "players", "level", "corners": [[lat, lon] x 6], "centre": [lat, lon]}.
    """
    who = {}
    for user_id, q, r in visits:
        who.setdefault((q, r), set()).add(user_id)
    cells = []
    for (q, r), players in who.items():
        if len(players) < MIN_PLAYERS:
            continue
        cells.append({"q": q, "r": r, "players": len(players), "level": level_of(len(players)),
                      "corners": [list(c) for c in hex_corners(q, r)], "centre": list(hex_centre(q, r))})
    cells.sort(key=lambda c: (-c["players"], c["q"], c["r"]))
    return cells


def summary_text(cells, days, hidden):
    """The sentence above the map. hidden: hexagons left out because too few players walked there."""
    if not cells:
        return (f"Not enough walkers yet: a spot shows once {MIN_PLAYERS} different players "
                f"have walked through it in the last {days} days.")
    spots = "1 busy spot" if len(cells) == 1 else f"{len(cells)} busy spots"
    quiet = ""
    if hidden:
        quiet = (" 1 quieter spot is hidden" if hidden == 1 else f" {hidden} quieter spots are hidden") + \
            " to keep paths private."
    return f"{spots} in the last {days} days.{quiet}"


def place_text(nearest):
    """The "Spot" column of the busiest-spots table."""
    return f"Near {nearest}" if nearest else "A spot with no treasure nearby"


def tip_text(cell, days, nearest=None):
    """The tooltip and table row for one hexagon."""
    where = f" near {nearest}" if nearest else ""
    return f"{cell['players']} players walked here{where} in the last {days} days"

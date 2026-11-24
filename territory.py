"""Claim the campus: hexagon tiles coloured by the team that walks them most (owner: B).

Plain Python with no Flask and no database, so it is easy to test.

The ground is cut into hexagons ("pointy-top", HEX_SIZE_M from the centre to a corner, so about
70 m across). Positions are turned into flat metres around ORIGIN, which is fine for one city.
A hexagon is named by two whole numbers (q, r), its "axial" coordinates.

Each day a player walks through a hexagon, it gets one visit for their team. The team with the
most visits this week owns it; a tie leaves it contested (no one's colour).
"""

import math

HEX_SIZE_M = 40
ORIGIN = (24.7955, 120.9965)        # NTHU: hexagon (0, 0) is centred here
M_PER_DEG_LAT = 111_320
TEAMS = {                            # id -> (name, colour)
    "gold": ("Gold", "#f2a93b"),
    "teal": ("Teal", "#4fc3b0"),
    "coral": ("Coral", "#d9622b"),
}
SQRT3 = math.sqrt(3)


def _m_per_deg_lon():
    return M_PER_DEG_LAT * math.cos(math.radians(ORIGIN[0]))


def to_metres(lat, lon):
    """(x east, y north) in metres from ORIGIN."""
    return (lon - ORIGIN[1]) * _m_per_deg_lon(), (lat - ORIGIN[0]) * M_PER_DEG_LAT


def to_latlon(x, y):
    return ORIGIN[0] + y / M_PER_DEG_LAT, ORIGIN[1] + x / _m_per_deg_lon()


def _round_hex(qf, rf):
    """The hexagon a fractional (q, r) falls in (round in cube coordinates, then fix the worst one)."""
    xf, zf = qf, rf
    yf = -xf - zf
    x, y, z = round(xf), round(yf), round(zf)
    dx, dy, dz = abs(x - xf), abs(y - yf), abs(z - zf)
    if dx > dy and dx > dz:
        x = -y - z
    elif dy > dz:
        y = -x - z
    else:
        z = -x - y
    return int(x), int(z)


def hex_of(lat, lon, size=HEX_SIZE_M):
    """(q, r) of the hexagon this point is in."""
    x, y = to_metres(lat, lon)
    return _round_hex((SQRT3 / 3 * x - y / 3) / size, (2 / 3 * y) / size)


def hex_centre(q, r, size=HEX_SIZE_M):
    return to_latlon(size * SQRT3 * (q + r / 2), size * 1.5 * r)


def hex_corners(q, r, size=HEX_SIZE_M):
    """The 6 corners as (lat, lon), for drawing the hexagon on the map."""
    cx, cy = size * SQRT3 * (q + r / 2), size * 1.5 * r
    corners = []
    for i in range(6):
        angle = math.radians(60 * i - 30)
        lat, lon = to_latlon(cx + size * math.cos(angle), cy + size * math.sin(angle))
        corners.append((round(lat, 6), round(lon, 6)))
    return corners


def parse_team(data):
    if not isinstance(data, dict) or data.get("team") not in TEAMS:
        raise ValueError(f"Choose a team: {', '.join(TEAMS)}")
    return data["team"]


def owners(visits):
    """{(q, r): team or None} from (q, r, team) visits. None = a tie (contested)."""
    counts = {}
    for q, r, team in visits:
        counts.setdefault((q, r), {}).setdefault(team, 0)
        counts[(q, r)][team] += 1
    out = {}
    for cell, by_team in counts.items():
        best = max(by_team.values())
        leaders = [t for t, n in by_team.items() if n == best]
        out[cell] = leaders[0] if len(leaders) == 1 else None
    return out


def scoreboard(owned, players_by_team):
    """Teams with how many hexagons they own, most first. players_by_team: {team: count}."""
    rows = [{"id": tid, "name": name, "colour": colour,
             "hexes": sum(1 for team in owned.values() if team == tid),
             "players": players_by_team.get(tid, 0)} for tid, (name, colour) in TEAMS.items()]
    return sorted(rows, key=lambda row: (-row["hexes"], row["name"]))


def leader(board):
    """The team in front, or None if nobody owns anything yet or the top two are level."""
    if not board or board[0]["hexes"] == 0 or (len(board) > 1 and board[1]["hexes"] == board[0]["hexes"]):
        return None
    return board[0]["id"]

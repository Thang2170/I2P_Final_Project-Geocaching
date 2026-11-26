"""Hunt replay: play a finished race back on the map (owner: B).

Plain Python with no Flask and no database, so it is easy to test.
replay_api.py saves each player's position while a race runs (one point every MIN_GAP_S
at most) and uses build_replay() to turn them into what the replay page draws.

The page only moves dots: Python decides the timeline, the speed, who won and how far
everyone walked.
"""

import math

from location import haversine_m

MIN_GAP_S = 5                 # keep at most one point every 5 seconds per player
MAX_POINTS = 720              # per player per race: one hour at one point every 5 s
REPLAY_LENGTH_S = 20          # a replay lasts about this long, whatever the race took
MAX_SPEED = 60                # ...but never faster than 60x (an hour-long race plays in a minute)
COLOUR_SLOTS = 8              # the replay page has 8 player colours; more players are grey


def should_keep(last_at, now, kept):
    """Save this point? Not if the last one was under MIN_GAP_S ago, or the race has enough."""
    if kept >= MAX_POINTS:
        return False
    return last_at is None or (now - last_at).total_seconds() >= MIN_GAP_S


def speed_for(duration_s):
    """How many times faster than real life, so the replay takes about REPLAY_LENGTH_S."""
    if duration_s <= REPLAY_LENGTH_S:
        return 1
    return min(MAX_SPEED, math.ceil(duration_s / REPLAY_LENGTH_S))


def path_length_m(points):
    """Metres along [t, lat, lon] points."""
    return sum(haversine_m(a[1], a[2], b[1], b[2]) for a, b in zip(points, points[1:]))


def clock(seconds):
    """3:05 for 185 s."""
    seconds = max(0, int(round(seconds)))
    return f"{seconds // 60}:{seconds % 60:02d}"


def build_replay(started_at, finished_at, paths, winner, treasure):
    """Everything the replay page needs.

    paths: {player name: [(when, lat, lon), ...]}. winner: the winner's name, or None.
    treasure: {"name", "lat", "lon"}. Points outside the race are dropped. The winner's
    path ends on the treasure at the finish, because that is where the race ended.
    Players are listed winner first, then by name, and each keeps that place (and colour).
    """
    duration_s = max(1, round((finished_at - started_at).total_seconds()))
    if winner is not None and winner not in paths:  # no saved path (map closed): still at the finish
        paths = {**paths, winner: []}
    players = []
    for name, rows in paths.items():
        points = sorted(([round((when - started_at).total_seconds(), 1), lat, lon]
                         for when, lat, lon in rows), key=lambda p: p[0])
        points = [p for p in points if 0 <= p[0] <= duration_s]
        if name == winner:
            points.append([duration_s, treasure["lat"], treasure["lon"]])
        if not points:
            continue
        walked = path_length_m(points)
        players.append({"name": name, "winner": name == winner, "points": points,
                        "walked_m": round(walked), "summary": _summary(name, name == winner, walked,
                                                                       duration_s)})
    players.sort(key=lambda p: (not p["winner"], p["name"].lower()))
    for i, player in enumerate(players):  # a fixed colour per player, never reused (grey after 8)
        player["slot"] = i + 1 if i < COLOUR_SLOTS else None
    speed = speed_for(duration_s)
    return {"duration_s": duration_s, "length": clock(duration_s), "speed": speed,
            "players": players, "treasure": treasure, "winner": winner,
            "headline": headline(winner, duration_s, len(players))}


def _summary(name, won, walked_m, duration_s):
    if won:
        return f"{name} won: {round(walked_m)} m in {clock(duration_s)}"
    return f"{name}: {round(walked_m)} m"


def headline(winner, duration_s, player_count):
    if player_count == 0:
        return "Nobody's path was saved for this race."
    if winner is None:
        return f"Race of {clock(duration_s)}, nobody won."
    return f"{winner} won the race in {clock(duration_s)}."


def replay_problem(state_finished, is_member):
    """Why this player may not watch the replay, or None."""
    if not is_member:
        return "Only players who were in this hunt can watch its replay."
    if not state_finished:
        return "The replay is ready once someone wins the race."
    return None

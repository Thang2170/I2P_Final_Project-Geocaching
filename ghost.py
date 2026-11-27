"""Ghost racing: race the fastest past run to a treasure, played back live beside you (owner: B).

A ghost is the winner's path from a finished hunt race (the race points replay.py keeps),
counted in seconds from the start. While you walk, the page sends how long you have been going
and where you are; Python says where the ghost is at that same second and who is ahead.

Plain Python with no Flask and no database, so it is easy to test.
"""

from location import FOUND_RADIUS_M, haversine_m
from replay import clock

NECK_AND_NECK_M = 10


def ghost_path(started_at, finished_at, points, treasure):
    """[(seconds, lat, lon), ...] from the start, ending at the treasure when the race was won.

    points: [(datetime, lat, lon), ...] in any order. Points before the start are dropped.
    """
    duration = max(1, round((finished_at - started_at).total_seconds()))
    path = sorted((round((when - started_at).total_seconds()), lat, lon) for when, lat, lon in points)
    path = [p for p in path if 0 <= p[0] <= duration]
    path.append((duration, treasure[0], treasure[1]))  # the winner reached it at the finish
    return path


def position_at(path, seconds):
    """Where the ghost is after this many seconds (in a straight line between its points)."""
    if seconds <= path[0][0]:
        return path[0][1], path[0][2]
    for (t1, lat1, lon1), (t2, lat2, lon2) in zip(path, path[1:]):
        if seconds <= t2:
            share = (seconds - t1) / (t2 - t1) if t2 > t1 else 1
            return lat1 + (lat2 - lat1) * share, lon1 + (lon2 - lon1) * share
    return path[-1][1], path[-1][2]


def fastest(runs):
    """The quickest run: runs are (name, duration_s, path). None if there are none."""
    return min(runs, key=lambda run: (run[1], run[0]), default=None)


def lead_text(my_left_m, ghost_left_m, ghost_name):
    lead = round(ghost_left_m - my_left_m)
    if abs(lead) < NECK_AND_NECK_M:
        return f"Neck and neck with {ghost_name}'s ghost!"
    if lead > 0:
        return f"You are {lead} m ahead of {ghost_name}'s ghost."
    return f"{ghost_name}'s ghost is {-lead} m ahead of you. Speed up!"


def finish_text(my_time_s, ghost_time_s, ghost_name):
    gap = round(my_time_s - ghost_time_s)
    if gap < 0:
        return f"You beat {ghost_name}'s ghost by {clock(-gap)}! Your time: {clock(round(my_time_s))}."
    if gap == 0:
        return f"A dead heat with {ghost_name}'s ghost: {clock(round(my_time_s))}."
    return f"{ghost_name}'s ghost won by {clock(gap)}. Your time: {clock(round(my_time_s))}. Try again?"


def compare(path, ghost_name, elapsed_s, lat, lon, treasure):
    """Everything the race page shows at this second."""
    ghost_lat, ghost_lon = position_at(path, elapsed_s)
    ghost_time = path[-1][0]
    my_left = haversine_m(lat, lon, treasure[0], treasure[1])
    ghost_left = 0 if elapsed_s >= ghost_time else haversine_m(ghost_lat, ghost_lon, treasure[0], treasure[1])
    arrived = my_left <= FOUND_RADIUS_M
    if arrived:
        text = finish_text(elapsed_s, ghost_time, ghost_name)
    elif elapsed_s >= ghost_time:
        text = f"{ghost_name}'s ghost got there in {clock(ghost_time)}. Keep going, you are {round(my_left)} m away."
    else:
        text = lead_text(my_left, ghost_left, ghost_name)
    return {"ghost": {"lat": round(ghost_lat, 6), "lon": round(ghost_lon, 6), "finished": elapsed_s >= ghost_time},
            "my_left_m": round(my_left), "ghost_left_m": round(ghost_left),
            "lead_m": round(ghost_left - my_left), "finished": arrived, "text": text,
            "clock": clock(max(0, round(elapsed_s)))}

"""Daily streaks and weekly challenges (owner: B).

Plain Python with no Flask and no database, so it is easy to test.

An "active day" is a day you found a treasure or finished a hunt. Days and weeks use Taiwan
time (UTC+8), so a walk at 7 a.m. counts for the right day. Weeks run Monday to Sunday.

The streak is how many active days in a row lead up to today. If you haven't walked yet today,
yesterday's streak is still alive until midnight.

Each weekly challenge pays CHALLENGE_REWARD coins once per week, when you claim it.
"""

from datetime import timedelta, timezone

LOCAL = timezone(timedelta(hours=8))  # Taiwan
CHALLENGE_REWARD = 15

# id -> (what it says, goal). The numbers come from week_numbers() below.
CHALLENGES = {
    "finds": ("Find 3 treasures", 3),
    "distance": ("Walk 2 km in finished hunts", 2000),
    "days": ("Be active on 4 different days", 4),
    "bounty": ("Find a bounty treasure (20+ coins)", 1),
}
BOUNTY_FROM = 20


def local_day(when):
    """The Taiwan date of a UTC time. SQLite drops the zone; we always save UTC."""
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return when.astimezone(LOCAL).date()


def week_start(day):
    """The Monday of the week that day is in."""
    return day - timedelta(days=day.weekday())


def streaks(active_days, today):
    """(current streak, best streak) from a set of dates you were active on."""
    days = set(active_days)
    # Not walked yet today? The streak from yesterday still counts until midnight.
    end = today if today in days else today - timedelta(days=1)
    current = 0
    while end - timedelta(days=current) in days:
        current += 1
    best, run, previous = 0, 0, None
    for day in sorted(days):
        run = run + 1 if previous is not None and day - previous == timedelta(days=1) else 1
        best = max(best, run)
        previous = day
    return current, max(best, current)


def week_numbers(finds, hunts, monday):
    """This week's numbers for the challenges.

    finds: (when, coins) for each treasure you found. hunts: (when, metres) for each finished hunt.
    """
    end = monday + timedelta(days=7)
    in_week = lambda when: monday <= local_day(when) < end  # noqa: E731 (a tiny helper)
    week_finds = [(w, c) for w, c in finds if in_week(w)]
    week_hunts = [(w, m) for w, m in hunts if in_week(w)]
    days = {local_day(w) for w, _ in week_finds} | {local_day(w) for w, _ in week_hunts}
    return {
        "finds": len(week_finds),
        "distance": round(sum(m for _, m in week_hunts)),
        "days": len(days),
        "bounty": sum(1 for _, c in week_finds if c >= BOUNTY_FROM),
    }


def challenge_list(numbers, claimed_ids):
    """Each challenge with its progress: what the welcome page shows."""
    out = []
    for cid, (title, goal) in CHALLENGES.items():
        progress = numbers.get(cid, 0)
        shown = min(progress, goal)
        text = f"{shown / 1000:.1f} / {goal / 1000:.0f} km" if cid == "distance" else f"{shown} / {goal}"
        out.append({"id": cid, "title": title, "goal": goal, "progress": shown, "text": text,
                    "done": progress >= goal, "claimed": cid in claimed_ids, "reward": CHALLENGE_REWARD})
    return out


def claim_problem(challenge_id, numbers, claimed_ids):
    """Why this claim can't be paid, or None if it can."""
    if challenge_id not in CHALLENGES:
        return "No such challenge"
    if challenge_id in claimed_ids:
        return "You already claimed this one this week"
    if numbers.get(challenge_id, 0) < CHALLENGES[challenge_id][1]:
        return "Not done yet: keep walking!"
    return None


def today_local(now):
    return local_day(now)


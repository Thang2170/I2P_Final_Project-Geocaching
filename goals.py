"""Health goals with milestones (owner: B). C's idea: pick a goal and earn milestones on the way.

Plain Python with no Flask and no database, so it is easy to test.

You pick one of three goals:
- "steps":  10,000 steps a week
- "active": 30 active minutes a day
- "rehab":  rehab walking: a gentle daily walk that starts short and grows each good week

The numbers come from what the app already saves: the band's readings (time, heart rate, steps)
and finished hunts (time, minutes, steps). Days and weeks are Taiwan time (streaks.py).
Each milestone pays its coins once per day or week, when you collect it.
"""

from collections import defaultdict
from datetime import timedelta

from streaks import local_day, week_start

READING_S = 5                 # the band sends one reading every 5 s
ACTIVE_FROM = 0.6             # "active" = at least 60% of your max heart rate
GENTLE_BELOW = 0.7            # rehab walks should stay under 70% of your max

REHAB_START_MIN = 10          # rehab: 10 minutes a day to begin with...
REHAB_STEP_MIN = 5            # ...5 more after each good week...
REHAB_MAX_MIN = 30            # ...up to 30
REHAB_GOOD_WEEK_DAYS = 5      # a good week: the daily walk done on 5 days

GOALS = {
    "steps": "10,000 steps a week",
    "active": "30 active minutes a day",
    "rehab": "Rehab walking",
}
GOAL_TEXT = {
    "steps": "Walk 10,000 steps over the week. Steps come from your band, or from your hunts.",
    "active": "Be active for 30 minutes every day: walking fast enough to reach 60% of your max "
              "heart rate (with the band), or time on hunts.",
    "rehab": "A short, gentle walk every day. It starts at 10 minutes and grows by 5 after every "
             "week you walk on 5 days, up to 30. Keep it easy, and follow your doctor's or physio's advice.",
}


def parse_goal(value):
    if value not in GOALS:
        raise ValueError(f"goal must be one of: {', '.join(GOALS)}")
    return value


# ---------------------------------------------------------------- daily numbers

def daily_numbers(band, hunts, hr_max):
    """{date: {"steps", "active_min", "walk_min", "hard_share"}} from the band and the hunts.

    band:  (when, heart rate or None, steps or None) for each reading
    hunts: (when, duration_s, steps) for each finished hunt
    On a day with band steps the band counts (it saw every step, hunts included); otherwise
    the hunts do. Minutes take the larger of the two, so a hunt with the band on counts once.
    """
    day = defaultdict(lambda: {"band_steps": 0, "has_band_steps": False, "active_s": 0, "moving_s": 0,
                               "readings": 0, "hard": 0, "hunt_steps": 0, "hunt_s": 0})
    for when, hr, steps in band:
        d = day[local_day(when)]
        if steps:
            d["band_steps"] += steps
            d["has_band_steps"] = True
            d["moving_s"] += READING_S
        if hr:
            d["readings"] += 1
            if hr >= ACTIVE_FROM * hr_max:
                d["active_s"] += READING_S
            if hr >= GENTLE_BELOW * hr_max:
                d["hard"] += 1
    for when, duration_s, steps in hunts:
        d = day[local_day(when)]
        d["hunt_steps"] += steps or 0
        d["hunt_s"] += duration_s or 0
    return {
        date: {
            "steps": d["band_steps"] if d["has_band_steps"] else d["hunt_steps"],
            "active_min": round(max(d["active_s"], d["hunt_s"]) / 60),
            "walk_min": round(max(d["moving_s"], d["hunt_s"]) / 60),
            "hard_share": round(d["hard"] / d["readings"], 2) if d["readings"] else 0.0,
        }
        for date, d in day.items()
    }


def _get(days, date, key):
    return days.get(date, {}).get(key, 0)


def week_dates(monday):
    return [monday + timedelta(days=i) for i in range(7)]


# ---------------------------------------------------------------- rehab level

def rehab_minutes(days, started_on, today):
    """Today's rehab target in minutes: 10, then +5 after each good week since you started."""
    target = REHAB_START_MIN
    monday = week_start(started_on)
    this_monday = week_start(today)
    while monday < this_monday:
        good_days = sum(1 for d in week_dates(monday) if _get(days, d, "walk_min") >= target)
        if good_days >= REHAB_GOOD_WEEK_DAYS:
            target = min(REHAB_MAX_MIN, target + REHAB_STEP_MIN)
        monday += timedelta(days=7)
    return target


# ---------------------------------------------------------------- milestones

def milestones(goal, days, today, started_on):
    """The milestones for this goal, today and this week.

    Each: id, title, period ("day" or "week"), period_start, progress, target, unit, reward.
    """
    monday = week_start(today)
    week = week_dates(monday)
    if goal == "steps":
        steps = sum(_get(days, d, "steps") for d in week)
        return [_m(f"steps-{n}", title, "week", monday, steps, n, "steps", reward)
                for n, title, reward in ((2500, "2,500 steps this week", 2), (5000, "Halfway: 5,000 this week", 3),
                                         (7500, "7,500 steps this week", 3), (10000, "10,000 steps this week!", 10))]
    if goal == "active":
        today_min = _get(days, today, "active_min")
        good_days = sum(1 for d in week if _get(days, d, "active_min") >= 30)
        return [_m(f"active-{n}", title, "day", today, today_min, n, "min", reward)
                for n, title, reward in ((10, "10 active minutes today", 1), (20, "20 active minutes today", 2),
                                         (30, "30 active minutes today!", 5))] + \
               [_m("active-week", "30 active minutes on 5 days this week", "week", monday, good_days, 5,
                   "days", 10)]
    if goal == "rehab":
        target = rehab_minutes(days, started_on, today)
        good_days = sum(1 for d in week if _get(days, d, "walk_min") >= target)
        return [_m("rehab-day", f"Today's gentle walk: {target} minutes", "day", today,
                   _get(days, today, "walk_min"), target, "min", 3),
                _m("rehab-week", f"{target}-minute walks on 5 days this week", "week", monday, good_days,
                   REHAB_GOOD_WEEK_DAYS, "days", 10)]
    raise ValueError("unknown goal")


def _m(mid, title, period, period_start, progress, target, unit, reward):
    return {"id": mid, "title": title, "period": period, "period_start": period_start,
            "progress": min(progress, target), "target": target, "unit": unit, "reward": reward,
            "done": progress >= target}


def find_milestone(goal, days, today, started_on, milestone_id):
    for m in milestones(goal, days, today, started_on):
        if m["id"] == milestone_id:
            return m
    return None


def rehab_advice(days, today, hr_max):
    """A gentle reminder if today's band readings were often above 70% of your max."""
    if _get(days, today, "hard_share") >= 0.25:
        return (f"Today your heart rate was above {round(GENTLE_BELOW * hr_max)} bpm for a good part of the "
                "walk. For rehab walking, slow down so you can still talk easily.")
    return None


def week_strip(goal, days, today, started_on):
    """Monday..Sunday: what you did each day, for the little week chart."""
    key = {"steps": "steps", "active": "active_min", "rehab": "walk_min"}[goal]
    daily_target = {"steps": None, "active": 30, "rehab": rehab_minutes(days, started_on, today)}[goal]
    out = []
    for d in week_dates(week_start(today)):
        value = _get(days, d, key)
        out.append({"date": d.isoformat(), "day": d.strftime("%a"), "value": value,
                    "met": daily_target is not None and value >= daily_target, "future": d > today})
    return out

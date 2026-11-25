"""Daily habits: the daily goal ring, streak freezes and sharing your streak (owner: B; C's idea #8).

Plain Python with no Flask and no database, so it is easy to test. Builds on streaks.py.

The ring: one number to close each day. It follows your goal (goals.py): 1,500 steps a day for
"10,000 steps a week", 30 active minutes for "30 active minutes a day", today's rehab walk for
"rehab walking", and 2,000 steps if you have not picked a goal. Closing the ring counts as an
active day for your streak, like finding a treasure or finishing a hunt.

Streak freezes: buy one for FREEZE_PRICE coins (hold at most MAX_FREEZES). If you miss a day,
a freeze you already had covers it automatically and the streak lives on. A freeze only covers
days after you bought it, so it can protect a streak but not bring back one that already broke.
"""

from datetime import timedelta

from goals import rehab_minutes

FREEZE_PRICE = 30
MAX_FREEZES = 2
LOOKBACK_DAYS = 60       # how far back ring days count for the streak

DEFAULT_RING = ("steps", 2000)
RING_FOR_GOAL = {"steps": ("steps", 1500), "active": ("active_min", 30)}
UNIT = {"steps": "steps", "active_min": "active min", "walk_min": "min walked"}


def ring_target(goal, days, day, started_on):
    """(which number, target) for that day."""
    if goal == "rehab":
        return "walk_min", rehab_minutes(days, started_on, day)
    return RING_FOR_GOAL.get(goal, DEFAULT_RING)


def ring(goal, days, today, started_on):
    """Today's ring: {"key", "value", "target", "percent", "closed", "unit", "text"}."""
    key, target = ring_target(goal, days, today, started_on)
    value = days.get(today, {}).get(key, 0)
    percent = min(100, round(100 * value / target)) if target else 0
    closed = value >= target
    unit = UNIT[key]
    left = target - value
    text = ("Ring closed! Today counts for your streak." if closed
            else f"{left:,} {unit} to close today's ring.")
    return {"key": key, "value": value, "target": target, "percent": percent, "closed": closed,
            "unit": unit, "text": text}


def ring_days(goal, days, today, started_on):
    """Every day (in the last LOOKBACK_DAYS) on which the ring was closed."""
    closed = set()
    for day in days:
        if today - timedelta(days=LOOKBACK_DAYS) <= day <= today:
            key, target = ring_target(goal, days, day, started_on)
            if days[day].get(key, 0) >= target:
                closed.add(day)
    return closed


def freezes_to_use(counted_days, frozen_days, today, unused_bought_days):
    """The missed days that unused freezes should cover now, oldest first.

    counted_days: days you were active (finds, hunts, closed rings)
    frozen_days:  days already covered by a freeze
    unused_bought_days: the day each unused freeze was bought
    Walks back from yesterday through your streak. Each gap is covered if there are enough
    freezes for the whole gap, each bought before the day it covers, and an active day comes
    before the gap (so there is a streak to save). It works even if you didn't open the app
    the day after you missed one.
    """
    covered = set(counted_days) | set(frozen_days)
    if not covered:
        return []
    bought = sorted(unused_bought_days)
    use = []
    day = today - timedelta(days=1)
    oldest = min(covered)
    while day >= oldest and bought:
        if day in covered:
            day -= timedelta(days=1)
            continue
        gap = []  # the missed days of this gap, newest first
        while day not in covered and day >= oldest:
            gap.append(day)
            day -= timedelta(days=1)
        if day < oldest or len(gap) > len(bought):
            break  # nothing before the gap, or not enough freezes: the streak ends here
        spare = list(bought)
        ok = True
        for missed in sorted(gap):
            usable = [b for b in spare if b < missed]  # bought before the day it covers
            if not usable:
                ok = False
                break
            spare.remove(usable[0])
        if not ok:
            break
        bought = spare
        use.extend(gap)
    return sorted(use)


def freeze_problem(owned_unused, balance):
    """Why you can't buy a freeze now, or None."""
    if owned_unused >= MAX_FREEZES:
        return f"You can hold at most {MAX_FREEZES} freezes."
    if balance < FREEZE_PRICE:
        return f"A freeze costs {FREEZE_PRICE} coins. You have {balance}."
    return None


def share_text(current, best, ring_closed):
    """The Community post for your streak, written by Python."""
    if current <= 0:
        raise ValueError("Start a streak first: find a treasure, finish a hunt or close your ring today.")
    days = f"{current}-day streak" if current != 1 else "1-day streak"
    text = f"🔥 I'm on a {days} on StepQuest!"
    if best > current:
        text += f" My best is {best} days, so I'm coming for it."
    elif current >= 3:
        text += " That's my best ever."
    if ring_closed:
        text += " Today's ring is closed too. ⭕"
    return text + " Who's walking with me?"


# ---------------------------------------------------------------- streak at risk (the evening reminder)

REMIND_FROM_HOUR = 20  # 8 p.m. Taiwan time: late enough to matter, early enough to still walk


def streak_at_risk(current, today_done, local_hour):
    """True if the bell should warn you tonight: you have a streak and nothing counted today yet."""
    return local_hour >= REMIND_FROM_HOUR and current >= 1 and not today_done


def streak_risk_text(current, freezes):
    """What the evening reminder says."""
    days = "1-day streak" if current == 1 else f"{current}-day streak"
    text = (f"🔥 Your {days} ends at midnight! Find a treasure, finish a hunt or close your ring "
            "today to keep it.")
    if freezes:
        text += f" (You have {freezes} freeze{'s' if freezes != 1 else ''} ready, so a missed day won't break it.)"
    return text

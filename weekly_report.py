"""The weekly health report (owner: B). Plain Python with no Flask and no database.

report_api.py gathers the week's numbers (from the band, hunts and trails); this module turns
them into the report: a bar per day, totals compared with last week, time in each heart-rate
zone, a few highlights in plain words, and the text for sharing it. Weeks run Monday to Sunday,
Taiwan time (streaks.py).
"""

from datetime import timedelta

from health import ZONE_NAMES

DAY_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def week_days(monday):
    return [monday + timedelta(days=i) for i in range(7)]


def change_text(now, before, unit, partial=False):
    """'+12% vs last week', 'same as last week', 'new this week' or ''.

    partial: the week isn't over, so it is compared with the same days of last week.
    """
    if not now and not before:
        return ""
    if not before:
        return "new this week"
    pct = round(100 * (now - before) / before)
    than = "the same days last week" if partial else "last week"
    if pct == 0:
        return f"same as {than}"
    return f"{'+' if pct > 0 else ''}{pct}% vs {than}"


def _total(days, dates, key):
    return sum(days.get(d, {}).get(key, 0) for d in dates)


def build_report(monday, today, days, ring, zone_seconds, hunts, trails, safety_stops, streak=None):
    """The report for the week starting `monday`.

    days:  {date: {"steps", "active_min", "walk_min"}} covering this week AND last week
    ring:  (key, target): today's daily ring, drawn as a line on the steps chart (key "steps" only)
    zone_seconds: [5 numbers]: seconds in each heart-rate zone this week (empty if no band)
    hunts, trails: [(distance_m, duration_s, calories)] finished this week
    streak: your current streak (only for the current week), else None
    """
    this_week = week_days(monday)
    last_week = week_days(monday - timedelta(days=7))
    bars = [{"date": d.isoformat(), "day": DAY_NAMES[i], "steps": days.get(d, {}).get("steps", 0),
             "active_min": days.get(d, {}).get("active_min", 0), "future": d > today, "today": d == today}
            for i, d in enumerate(this_week)]

    # A week still going is compared with the same days of last week (Mon-Thu with Mon-Thu), not all 7
    partial = monday <= today < this_week[-1]
    upto = (today - monday).days + 1 if partial else 7
    steps, steps_before = _total(days, this_week, "steps"), _total(days, last_week[:upto], "steps")
    active, active_before = _total(days, this_week, "active_min"), _total(days, last_week[:upto], "active_min")
    walks = hunts + trails
    calories = round(sum(c for _, _, c in walks))
    distance_m = round(sum(d for d, _, _ in walks))

    zones = [{"zone": i, "name": ZONE_NAMES[i], "minutes": round(s / 60)} for i, s in enumerate(zone_seconds)]
    ring_key, ring_target = ring
    totals = {
        "steps": steps, "steps_change": change_text(steps, steps_before, "steps", partial),
        "active_min": active, "active_change": change_text(active, active_before, "min", partial),
        "hunts": len(hunts), "trails": len(trails), "distance_m": distance_m, "calories": calories,
        "safety_stops": safety_stops, "streak": streak,
        "ring_days": sum(1 for b in bars if ring_key == "steps" and b["steps"] >= ring_target),
    }
    return {
        "week_start": monday.isoformat(),
        "week_end": this_week[-1].isoformat(),
        "is_current": monday <= today <= this_week[-1],
        "bars": bars,
        "ring": {"key": ring_key, "target": ring_target} if ring_key == "steps" else None,
        "totals": totals,
        "zones": zones if any(z["minutes"] for z in zones) else [],
        "highlights": highlights(bars, totals, zones, ring_key, ring_target),
    }


def highlights(bars, totals, zones, ring_key, ring_target):
    """A few sentences about the week, written by Python."""
    out = []
    best = max(bars, key=lambda b: b["steps"])
    if best["steps"]:
        out.append(f"Best day: {best['day']} with {best['steps']:,} steps.")
    if totals["steps_change"] and totals["steps_change"] != "new this week":
        out.append(f"Steps: {totals['steps_change']}.")
    if ring_key == "steps" and totals["ring_days"]:
        out.append(f"You closed your {ring_target:,}-step ring on {totals['ring_days']} "
                   f"day{'s' if totals['ring_days'] != 1 else ''}.")
    bonus = sum(z["minutes"] for z in zones if z["zone"] in (1, 2))
    if bonus:
        out.append(f"{bonus} min in the 60–80% heart-rate zone, the best one for fitness.")
    hard = sum(z["minutes"] for z in zones if z["zone"] >= 3)
    if hard >= 20:
        out.append(f"{hard} min in the Hard or Maximum zones: remember to rest between hard days.")
    if totals["safety_stops"]:
        out.append(f"{totals['safety_stops']} safety stop{'s' if totals['safety_stops'] != 1 else ''} this week. "
                   "If you felt unwell, talk to a doctor.")
    if not out:
        out.append("A quiet week. Plan a trail on the map to get going!")
    return out


def share_text(report):
    """The Community post for the week (no health details: just steps, walks and the streak)."""
    t = report["totals"]
    text = f"📊 My StepQuest week: {t['steps']:,} steps"
    if t["steps_change"] and t["steps_change"] != "new this week":
        text += f" ({t['steps_change']})"
    walks = t["hunts"] + t["trails"]
    if walks:
        text += f", {walks} walk{'s' if walks != 1 else ''} ({t['distance_m'] / 1000:.1f} km)"
    if t["streak"]:
        text += f", and a {t['streak']}-day streak 🔥"
    return text + "."

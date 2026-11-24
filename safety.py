"""Safety alerts from the band during a hunt (owner: B; C's idea #7).

Plain Python with no Flask and no database, so it is easy to test.

Readings are (time, heart rate or None, SpO2 or None), oldest first. Python looks at the last
couple of minutes and answers with a level:
- "stop":    stop the hunt now and show a clear warning (the map does this)
- "caution": keep an eye on it (a gentle line on the map)
- "ok"

One odd reading is often the sensor slipping, so "stop" always needs the problem to last:
- blood oxygen (SpO2) below LOW_SPO2 (92%, from health.py) on STOP_SPO2_READINGS readings in a row
- heart rate above your max (from your age) for HIGH_HR_S seconds without a break
- heart rate below LOW_HR while you are walking, for LOW_HR_S seconds without a break

This is a game, not a medical device: the warning always says so and gives the emergency number.
"""

from health import LOW_SPO2

READING_S = 5                 # one band reading every 5 s
MAX_GAP_S = 15                # readings further apart than this are not "in a row"

STOP_SPO2_READINGS = 3        # three low readings in a row (about 15 s)
CAUTION_SPO2 = 94             # 92-94%: worth watching
HIGH_HR_S = 30                # above your max heart rate for 30 s
HIGH_HR_MARGIN = 5            # ...by more than 5 bpm (the max is only an estimate)
LOW_HR = 40                   # under 40 bpm while walking is unusual
LOW_HR_S = 30

EMERGENCY_NUMBER = "119"      # Taiwan: ambulance and fire
NOT_MEDICAL = "StepQuest is a game, not a medical device."


def _streak_seconds(readings, bad):
    """How long the newest readings have been bad without a break (seconds), and how many."""
    count, first, newer = 0, None, None
    for when, value in reversed(readings):
        if value is None:
            continue
        if not bad(value) or (newer is not None and (newer - when).total_seconds() > MAX_GAP_S):
            break
        count += 1
        first = when
        newer = when
    if not count:
        return 0, 0
    return round((readings[-1][0] - first).total_seconds()) + READING_S, count


def check(readings, hr_max):
    """{"level", "reason", "title", "text", "advice", "hr", "spo2"} for the latest readings."""
    hrs = [(when, hr) for when, hr, _ in readings if hr is not None]
    oxygen = [(when, spo2) for when, _, spo2 in readings if spo2 is not None]
    hr = hrs[-1][1] if hrs else None
    spo2 = oxygen[-1][1] if oxygen else None
    base = {"hr": hr, "spo2": spo2}

    _, low_count = _streak_seconds(oxygen, lambda v: v < LOW_SPO2)
    if low_count >= STOP_SPO2_READINGS:
        return base | _stop(
            "low_spo2", f"Low blood oxygen: {spo2:.0f}%",
            f"Your band has read your blood oxygen below {LOW_SPO2}% for a while (now {spo2:.0f}%).")

    high_s, _ = _streak_seconds(hrs, lambda v: v > hr_max + HIGH_HR_MARGIN)
    if high_s >= HIGH_HR_S:
        return base | _stop(
            "high_hr", f"Heart rate too high: {hr} bpm",
            f"Your heart rate has been above your estimated maximum ({hr_max} bpm) for {high_s} seconds.")

    low_s, _ = _streak_seconds(hrs, lambda v: v < LOW_HR)
    if low_s >= LOW_HR_S:
        return base | _stop(
            "low_hr", f"Heart rate unusually low: {hr} bpm",
            f"Your band has read a heart rate under {LOW_HR} bpm for {low_s} seconds while you are walking.")

    if spo2 is not None and spo2 < CAUTION_SPO2:
        return base | {"level": "caution", "reason": "spo2_watch", "title": f"Blood oxygen {spo2:.0f}%",
                       "text": "A little low. Slow down and breathe deeply. If the band is loose, tighten it.",
                       "advice": []}
    if hr is not None and hr > hr_max:
        return base | {"level": "caution", "reason": "hr_watch", "title": f"Heart rate {hr} bpm",
                       "text": "Above your estimated maximum. Slow down to a walk.", "advice": []}
    return base | {"level": "ok", "reason": None, "title": "", "text": "", "advice": []}


def _stop(reason, title, text):
    return {
        "level": "stop", "reason": reason, "title": title,
        "text": f"{text} Your hunt has been stopped. {NOT_MEDICAL}",
        "advice": [
            "Stop walking and sit down somewhere safe.",
            "Breathe slowly. Check that the band sits snugly on your wrist: a loose band misreads.",
            f"If you feel chest pain, short of breath, faint or confused, call {EMERGENCY_NUMBER} now.",
            "Tell someone nearby how you feel. Don't start another hunt until you feel normal.",
        ],
    }

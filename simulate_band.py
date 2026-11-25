"""Pretend to be the band, LIVE: one reading every 5 seconds, for demos on stage (owner: B).

A's esp32/simulate_walk.py sends a finished walk all at once (good for the Health page).
This one keeps sending while you show the live features: the heart-rate zone on the map,
the too-hard warnings, the cool-down quest and the safety stops. The readings come from
band_scenarios.py.

    python simulate_band.py --list
    python simulate_band.py zone --token YOUR_DEVICE_TOKEN
    python simulate_band.py low-spo2 --token YOUR_DEVICE_TOKEN --minutes 2

Get a token on the Health page ("Pair a new band"), or put it in the environment variable
STEPQUEST_BAND_TOKEN so you don't have to type it. Stop it with Ctrl+C.
Use --age with the age saved on the Health page, so the zones come out right.
"""

import argparse
import os
import sys
import time

import requests
import urllib3

from band_scenarios import EVERY_S, SCENARIOS, backfill, reading_at

DEFAULT_SERVER = "https://127.0.0.1:5000"  # app.py runs with HTTPS (a self-made certificate)


def post(server, token, readings, poster=requests.post):
    """Send readings to the app. Returns an error message, or None if it worked."""
    try:
        response = poster(server.rstrip("/") + "/api/health/readings", json={"readings": readings},
                          headers={"Authorization": f"Bearer {token}"}, timeout=10,
                          verify=False)  # the app's local certificate is self-made
    except requests.RequestException as err:
        return f"Could not reach {server} ({err.__class__.__name__}). Is the app running?"
    if response.status_code == 401:
        return "The app doesn't know this token: pair a band on the Health page and copy its token."
    if response.status_code != 201:
        return f"The app said {response.status_code}: {response.text[:200]}"
    return None


def run(scenario, server, token, minutes, age, fill=True, poster=requests.post, sleep=time.sleep, say=print):
    """Send the scenario live. Returns how many readings were sent (stops early on an error)."""
    what, how, _, _ = SCENARIOS[scenario]
    say(f"Band simulator: {scenario} ({what}), age {age}, for {minutes:g} min. Ctrl+C to stop.")
    say(f"What to look at: {how}")
    sent = 0
    if fill:
        earlier = backfill(scenario, age)
        if earlier:
            problem = post(server, token, earlier, poster)
            if problem:
                say(problem)
                return sent
            sent += len(earlier)
            say(f"Sent the last {len(earlier) * EVERY_S // 60} min at once, as if the band had been on.")
    for n in range(int(minutes * 60 / EVERY_S)):
        t = n * EVERY_S
        reading = reading_at(scenario, t, age) | {"age_s": 0}
        problem = post(server, token, [reading], poster)
        if problem:
            say(problem)
            return sent
        sent += 1
        say(f"  {t // 60:02d}:{t % 60:02d}  heart {reading['hr']} bpm  SpO2 {reading['spo2']}%  steps +{reading['steps']}")
        sleep(EVERY_S)
    say(f"Done: {sent} readings sent.")
    return sent


def main(argv=None, **kwargs):
    parser = argparse.ArgumentParser(description="Pretend to be the StepQuest band, live (for demos).")
    parser.add_argument("scenario", nargs="?", choices=sorted(SCENARIOS), help="what to pretend")
    parser.add_argument("--list", action="store_true", help="show the scenarios and what each shows")
    parser.add_argument("--token", default=os.environ.get("STEPQUEST_BAND_TOKEN"),
                        help="from the Health page (or set STEPQUEST_BAND_TOKEN)")
    parser.add_argument("--server", default=DEFAULT_SERVER)
    parser.add_argument("--minutes", type=float, default=10)
    parser.add_argument("--age", type=int, default=20, help="the age saved on the Health page")
    parser.add_argument("--no-backfill", action="store_true", help="don't send the earlier minutes first")
    args = parser.parse_args(argv)
    say = kwargs.get("say", print)
    if args.list or not args.scenario:
        for name, (what, how, fill, _) in SCENARIOS.items():
            say(f"{name:9} {what}{f' (sends the last {fill // 60} min first)' if fill else ''}\n          {how}")
        return 0
    if not args.token:
        say("No token: add --token YOUR_TOKEN (Health page > Pair a new band), or set STEPQUEST_BAND_TOKEN.")
        return 2
    if not 0 < args.minutes <= 120 or not 10 <= args.age <= 100:
        say("--minutes must be 0-120 and --age 10-100.")
        return 2
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    try:
        run(args.scenario, args.server, args.token, args.minutes, args.age, not args.no_backfill, **kwargs)
    except KeyboardInterrupt:
        say("\nStopped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

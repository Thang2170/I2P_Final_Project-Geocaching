"""Pretend to be the ESP32 band: send a realistic walk to StepQuest (owner: A).

Use it to demo the Health page before the hardware arrives, or to test the server.

    python esp32/simulate_walk.py --server http://127.0.0.1:5000 --token YOUR_DEVICE_TOKEN

(Get a token on the Health page: "Pair a new band".) It sends one reading every 5 seconds of
a 20-minute walk, all at once, as if the band uploaded the walk afterwards (age_s says how
long ago each reading was taken). Runs on the PC with normal Python, not on the ESP32.
"""

import argparse
import math
import random

import requests

EVERY_S = 5


def fake_walk(minutes=20, seed=None):
    """Readings for a walk: warm up, a brisk middle part with a hill, and a cool-down."""
    rng = random.Random(seed)
    total = int(minutes * 60 / EVERY_S)
    readings = []
    for i in range(total):
        part = i / total
        effort = 0.35 + 0.45 * math.sin(math.pi * part) + (0.25 if 0.45 < part < 0.6 else 0)   # the hill
        hr = round(72 + 70 * effort + rng.uniform(-3, 3))
        steps_per_s = 1.5 + 0.6 * effort
        readings.append({
            "age_s": (total - i) * EVERY_S,              # oldest first
            "hr": hr,
            "spo2": round(rng.uniform(96.0, 98.5), 1),
            "steps": round(steps_per_s * EVERY_S + rng.uniform(-1, 1)),
            "temp_c": round(33.0 + effort + rng.uniform(-0.2, 0.2), 1),
        })
    return readings


def send(server, token, readings, batch=120):
    url = server.rstrip("/") + "/api/health/readings"
    sent = 0
    for start in range(0, len(readings), batch):
        response = requests.post(url, json={"readings": readings[start:start + batch]},
                                 headers={"Authorization": f"Bearer {token}"}, timeout=20, verify=False)
        if response.status_code != 201:
            raise SystemExit(f"The server said {response.status_code}: {response.text[:200]}")
        sent += response.json()["saved"]
    return sent


def main():
    parser = argparse.ArgumentParser(description="Send a pretend walk from the StepQuest band.")
    parser.add_argument("--server", default="http://127.0.0.1:5000")
    parser.add_argument("--token", required=True, help="from the Health page: Pair a new band")
    parser.add_argument("--minutes", type=float, default=20)
    args = parser.parse_args()
    readings = fake_walk(args.minutes)
    print(f"Sent {send(args.server, args.token, readings)} readings ({args.minutes:g} min walk). "
          "Open the Health page to see it.")


if __name__ == "__main__":
    main()

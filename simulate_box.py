"""Pretend to be a treasure box: show its 6-number code on your laptop (owner: B).

For a demo without the ESP32 box (esp32/box_main.py). It reads the box's secret straight from
the app's database, so the secret is never typed, pasted or written in any file.

    python simulate_box.py --list          # the treasures that have a box
    python simulate_box.py "Gate box"      # show its code; a new one every 30 seconds (Ctrl+C stops)

Set the BOX_SECRET environment variable instead to show the code for that secret.
"""

import argparse
import os
import sys
import time

from box_code import code_at, seconds_left


def boxes(flask_app):
    from models import Treasure, TreasureBox, db
    with flask_app.app_context():
        rows = db.session.execute(db.select(Treasure.name, TreasureBox.secret)
                                  .join(TreasureBox, TreasureBox.treasure_id == Treasure.id)
                                  .order_by(Treasure.name)).all()
    return dict(rows)


def screen(secret, now):
    """One line of the pretend box's screen."""
    code = code_at(secret, now)
    left = seconds_left(now)
    return f"  {code[:3]} {code[3:]}   [{'#' * left}{'.' * (30 - left)}] {left:2d}s"


def main(argv=None, say=print, flask_app=None, clock=time.time, sleep=time.sleep, ticks=None):
    parser = argparse.ArgumentParser(description="Show a treasure box's changing code.")
    parser.add_argument("treasure", nargs="?", help="the treasure's name (see --list)")
    parser.add_argument("--list", action="store_true", help="list the treasures that have a box")
    args = parser.parse_args(argv)

    secret = os.environ.get("BOX_SECRET")
    if secret is None or args.list:
        if flask_app is None:
            from app import app as flask_app  # the real database (instance/geohunt.db); loaded only here
        found = boxes(flask_app)
        if args.list or not args.treasure:
            say("Treasures with a box: " + (", ".join(found) or "none yet (make one on the Box page)"))
            return 0
        secret = found.get(args.treasure)
        if secret is None:
            say(f'No box at "{args.treasure}". Try --list.')
            return 1
    say(f"Box at {args.treasure or 'BOX_SECRET'}. Type the code on the Box page. Ctrl+C stops.")
    shown = None
    try:
        while ticks is None or ticks > 0:
            line = screen(secret, clock())
            if line != shown:
                say(line)
                shown = line
            if ticks is not None:
                ticks -= 1
            sleep(1)
    except KeyboardInterrupt:
        say("Box switched off.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

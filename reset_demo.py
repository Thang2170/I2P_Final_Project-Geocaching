"""Reset the demo before a rehearsal:  python reset_demo.py  (owner: B)

Deletes demo_player, alice and ben with everything they did, then seeds the demo story again,
so demo_player is back to 60 coins with nothing found. Other players are kept.

Add the names of players you registered during the rehearsal to remove them too:

    python reset_demo.py --also stage_player test1

It asks before deleting; --yes skips the question. Works while the app is running.
"""

import argparse
import sys

from demo_content import DEMO_PASSWORD
from demo_reset import demo_usernames, reset_demo


def main(argv=None, answer=input, say=print, flask_app=None):
    parser = argparse.ArgumentParser(description="Reset the StepQuest demo to the start of the story.")
    parser.add_argument("--also", nargs="*", default=[], metavar="USERNAME",
                        help="more players to delete (e.g. the one you registered on stage)")
    parser.add_argument("--yes", action="store_true", help="don't ask first")
    args = parser.parse_args(argv)
    names = demo_usernames(args.also)
    if not args.yes:
        reply = answer(f"Delete {', '.join(names)} and everything they did, then reload the demo? [y/N] ")
        if reply.strip().lower() not in ("y", "yes"):
            say("Nothing was changed.")
            return 1
    if flask_app is None:
        from app import app as flask_app  # the real database (instance/geohunt.db); loaded only here
    with flask_app.app_context():
        result = reset_demo(args.also)
    say(f"Removed: {', '.join(result['removed']) or 'nobody (they did not exist yet)'}")
    rows = sum(n for table, n in result["deleted"].items() if table != "users")
    say(f"Deleted {rows} rows of their activity.")
    say(f"Demo reloaded. Log in as demo_player, password {DEMO_PASSWORD}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

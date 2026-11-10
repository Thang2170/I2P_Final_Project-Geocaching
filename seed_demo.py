"""Load the demo data into the real database. Run it with:  python seed_demo.py

Safe to run more than once. To start completely fresh, stop the app, delete the file
instance/geohunt.db, then run the app (or this script) again.
"""

from app import app
from demo_content import DEMO_PASSWORD
from demo_data import seed_demo_story

if __name__ == "__main__":
    with app.app_context():
        added = seed_demo_story()
    for kind, names in added.items():
        print(f"{kind}: {', '.join(names) if names else 'nothing new'}")
    print(f"Log in as demo_player with password {DEMO_PASSWORD}")

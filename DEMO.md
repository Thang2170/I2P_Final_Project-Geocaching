# Demo guide (owner: B)

## Get a clean demo database
1. Stop the app.
2. Delete `instance/geohunt.db`.
3. Run `python seed_demo.py` (safe to run again; it only adds what is missing).
4. Run `python app.py` and open http://127.0.0.1:5000

## Accounts (all use password `demo1234`)
- `demo_player`: 60 coins, ready to shop. Log in with this one on stage.
- `alice`: hid the extra treasures.
- `ben`: fills the demo hunt.

## The story (about 3 minutes)
1. Register a new player. The map opens.
2. Hide a treasure from the Upload page. Try a spot within 10 m of another one to show the rule.
3. Walk to a treasure (or use the drag mode) and tap "I found it": +10 coins.
4. Shop: with too few coins the purchase is refused. Log in as `demo_player` and buy a voucher: you get a code.
5. Hunts: join "Full house (demo)". It has 2 places and both are taken, so you wait in line (position 1).
6. Walk stats: enter a weight to see steps and calories.

`python -m unittest test_demo_story` plays steps 1 to 5 automatically.

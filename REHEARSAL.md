# Rehearsal checklist (owner: B)

Do this the day before, and again 30 minutes before presenting.

## 1. Set up (5 minutes)
- [ ] `git checkout main` and `git pull` (everyone's work is merged)
- [ ] Activate the venv, then `pip install -r requirements.txt`
- [ ] `python -m unittest discover -p "test_*.py"` shows `OK`
- [ ] Stop the app, delete `instance/geohunt.db`, run `python seed_demo.py`, then `python app.py`
- [ ] Open http://127.0.0.1:5000 in a fresh browser window (or a private window)

## 2. Run the story once, out loud (3 minutes)
Follow the story in `DEMO.md`. Time it. Keep each step short.
- [ ] Register a new player, the map opens
- [ ] Hide a treasure; show the 10 m rule once
- [ ] Find a treasure with `/?drag` (no walking needed): +10 coins
- [ ] Shop: refused with too few coins; as `demo_player`, buy a voucher and read out the code
- [ ] Hunts: join "Full house (demo)" and show "waiting, position 1"
- [ ] Walk stats: enter a weight, see steps and calories

## 3. Things that go wrong on the day
| Problem | Fix |
|---|---|
| The map is blank | Check the internet: the map tiles come from the web |
| "Log in first" everywhere | Log in again; the session may have been cleared |
| The browser asks for your location and you can't walk | Use `/?drag` and drag the marker, or `/?fake=24.795324,120.994796` |
| The demo went wrong halfway | Stop the app, delete `instance/geohunt.db`, run `python seed_demo.py`, start again |
| `python` is not recognised | The venv is not active: run `venv\Scripts\Activate.ps1` |
| Port 5000 is busy | Close the other app window, or restart the terminal |

## 3b. If the app will not start at all
Keep a screen recording of one good run on your phone or laptop as a backup.

## 4. Who says what (fill in together)
- A: the map, routes and the idea
- B: accounts, treasures, coins, shop, hunts and the database
- C: the landing page, steps and calories

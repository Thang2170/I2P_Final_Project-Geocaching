# Demo guide (owner: B)

## Get a clean demo database
1. Stop the app.
2. Delete `instance/geohunt.db`.
3. Run `python seed_demo.py` (safe to run again; it only adds what is missing).
4. Run `python app.py` and open https://127.0.0.1:5000 (the browser warns about the test certificate the first time: choose Advanced, then Proceed)

## Reset between rehearsals (no need to stop the app)
```powershell
python reset_demo.py                          # demo_player, alice and ben back to the start
python reset_demo.py --also stage_player      # ...and remove a player you registered on stage
```
It deletes the demo players with everything they did (coins, finds, hunts, trails, posts, the
treasures they hid) and loads the demo again. Other players are kept. It asks first (`--yes` skips).

## Accounts (all use password `demo1234`)
- `demo_player`: 60 coins, ready to shop. Log in with this one on stage.
- `alice`: hid the extra treasures. Chats in "NTHU campus walk".
- `ben`: fills the demo hunt. Chats in "NTHU campus walk".

`demo_player` has already "seen" the welcome tour, so it won't pop up mid-demo.
To show it on purpose, open `/?tour`.

## The story (about 3 minutes)
1. Register a new player. The map opens.
2. Hide a treasure from the Upload page. Try a spot within 10 m of another one to show the rule.
3. Walk to a treasure (or use the drag mode) and tap "I found it": +10 coins.
4. Shop: with too few coins the purchase is refused. Log in as `demo_player` and buy a voucher: you get a code.
5. Hunts: join "Full house (demo)". It has 2 places and both are taken, so you wait in line (position 1).
   Then join "NTHU campus walk" (there is room) and tap **Open group chat**: alice and ben are already talking.
6. Walk stats: enter a weight to see steps and calories.

`python -m unittest tests.test_demo_story` plays steps 1 to 5 automatically.

## New ways to play (about 2 minutes; Menu > "New ways to play")
Indoors, add `?drag` to any of these addresses: the page then uses a pretend position instead of GPS.
1. **Wandering treasure** (`/wanderer`): show the footprints (yesterday, 12, 6 and 3 hours ago) and ask
   where it is heading. Logged in as an admin, `/wanderer?reveal=1&drag` shows where it really is:
   tap there on the map, then "Catch it here" (+30 coins, once a day).
2. **Ghost race** (`/ghost?drag`): race ben's ghost to the demo treasure. Press Start, then tap
   "Step closer" faster than the ghost walks: "You beat ben's ghost by ...".
3. **Team treasure** (`/team?drag`): "Twin benches" needs 2 players. Tap "I'm here" as demo_player,
   then within a minute on a second phone (or a private window) as alice: it opens for both (+15 each).
4. **Travelers** (`/travelers?drag`): the Golden Duck waits at Cafe corner and wants to reach Library steps.
   Choose "Cafe corner", pick it up, choose "Library steps", drop it: goal reached, +25 coins.
5. **Treasure box** (`/box`): in a second terminal run `python simulate_box.py "Gate box"` (or use the
   ESP32 with `esp32/box_main.py`). Type the code shown: "Proved!". Try the same code as another player:
   refused, each code works once. Finding "Gate box" on the map is refused until the code is typed.
6. **Eyes-free mode** (`/eyes-free?drag`): pick a treasure, tap Start, and turn the sound up. Tap
   "Step closer": the beeps speed up, and the phone says how far and which way.

`python -m unittest tests.test_demo_play` plays steps 3 to 5 automatically.

## Show the band's live features without the band
`simulate_band.py` pretends to be the band, sending one reading every 5 seconds while you demo.
(A's `esp32/simulate_walk.py` sends a finished walk instead: use that for the Health page.)

1. Log in, open the **Health** page, tap **Pair a new band** and copy the token.
2. In a second terminal, with the app running:
   ```powershell
   $env:STEPQUEST_BAND_TOKEN = "PASTE-THE-TOKEN"
   python simulate_band.py --list          # the scenarios and what each one shows
   python simulate_band.py zone            # then start a journey on the map
   ```
3. Good ones for stage:
   - `zone`: the map's journey panel shows the zone and bonus minutes; saving the hunt pays bonus coins.
   - `hard` or `maximum`: the red "too hard for too long" warning appears straight away.
   - `low-spo2`: start a journey first; after about 35 seconds the hunt stops with the safety warning.
   - `cooldown`: save a hunt first; the cool-down quest fills up and pays +3 after 3 minutes.
4. Ctrl+C stops it. If the zones look wrong, pass `--age` with the age saved on the Health page.

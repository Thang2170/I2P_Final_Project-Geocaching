# First pitch script (11/24)

2 minutes of pitch with 7 slides, then a 3-minute live demo.
Each person explains the part they built, so the judges can see we understand our own code.

- **A**: map and location (`location.py`, `routing.py`, `route_api.py`, `map.html`)
- **B**: data and backend (`app.py`, `models.py`, `coins.py`, the `*_api.py` Blueprints)
- **C**: UI, maths and tests (`calculator.py`, templates and CSS, `tests/`)

The spoken pitch is about 225 words: just under 2 minutes at a calm speed. Don't add lines; rehearse with a timer.

---

## Part 1: Pitch (2:00)

### Slide 1, cover (A, 0:00 to 0:12)
> Hi, we're StepQuest. I'm A, I built the map and the routes. B built the database and backend, and C built the pages, the maths and the tests.

### Slide 2, the problem (A, 0:12 to 0:27)
> Walking is healthy, but without a goal people don't go out. StepQuest hides treasures around you: walk to one, earn coins, and join a hunt so you're not walking alone.

### Slide 3, how it works (A, 0:27 to 0:55)
> Here's the key idea. The phone only reads GPS and draws the map. It sends a raw latitude and longitude to Flask, and Python decides: the haversine formula measures the distance, and within 20 metres you've found it. Routes come from OpenRouteService, and if that fails, Python falls back to straight lines.

**Hand-off:** "B, what happens inside the server?"

### Slide 4, inside one request (B, 0:55 to 1:25)
> Every feature has three layers. To claim a treasure, the Blueprint checks you're logged in. The rule, `coins.claim_problem`, is plain Python: not your own treasure, not twice, not over 20 metres. Then `models.py` saves ten coins in SQLite. Plain rules are easy to test: we have 614 tests, and none of them call the real routing API.

**Hand-off:** "C wrote the maths behind the numbers you'll see."

### Slide 5, the maths (C, 1:25 to 1:45)
> I wrote `calculator.py`. Steps are metres divided by 0.75, one average step. Calories are 0.5 times your weight times kilometres. So one kilometre at 60 kilos is 1,333 steps and 30 calories.

### Slide 6, where we are (C, 1:45 to 2:00)
> Features 1 to 6 work, and hunts, coins and the shop are done early. The street warning and QR scan come next. Let's show you.

**Switch to the browser** (slide 7 stays up while A switches).

---

## Part 2: Live demo (3:00)

**Driver:** A at the laptop. B and C talk when it's their part, and point at the screen.

### Before you go on stage
1. On the latest `main`: `python -m unittest` shows `OK`.
2. For a clean demo, stop the app, delete `instance\geohunt.db`, run `python seed_demo.py`, then `python app.py`.
3. Log in as `demo_player` (password in `DEMO.md`). This player starts with 60 coins.
4. Open only **one** map tab: `/?fake=24.7955,120.9965` (about 170 m from the first treasure).
5. Keep the second address in a note, ready to paste: `/?fake=24.795324,120.994796`. **Don't open it early.** Opening it pays the +10 coins straight away, and then there is nothing to show on stage.
6. Set your routing key (`ORS_API_KEY`), or the route will be dashed straight lines. Either is fine to show.

### 0:00 to 0:40, A: location and route
- Show the map: your marker, the treasure chests and the orange walking route.
- Point at the box at the bottom: "173 m to National Tsing Hua University, 0.31 km walk, about 4 minutes."
> The 173 metres is the straight line from haversine. The walk is longer because the route follows real paths. Both numbers come from Python.
- Press **New route** twice: a different path to the same treasure each time.
> Python picks a random side-step point beside the straight line, and the route goes through it. Once you reach that point, the route goes straight to the treasure.

### 0:40 to 1:10, A then B: find the treasure
- A pastes the second address: you are now standing on the treasure.
- The box says **"You found National Tsing Hua University"** and the coins go from 60 to 70 (+10).
- B: "The server checked the 20-metre rule, then saved the coins. It never pays the same treasure twice."
- Reload the page: the found treasure has disappeared, and the map now aims at the next one, Pond bench.

### 1:10 to 1:50, B: hide a new treasure (Hide a treasure page)
- B: "Players make the game bigger by hiding their own treasures."
- The small map opens on campus. Tap an empty spot, type a name and a hint (the photo is optional), and save.
- Then tap right on top of an existing chest and save again: it's refused.
> Python checks that treasures are at least 10 metres apart, so two can't sit on the same spot.

### 1:50 to 2:30, C: steps and calories
- Go back to the map by pasting the second address again (plain `/` would ask for real GPS).
- C points at the route box: steps and kcal for the walk to Pond bench.
> These are the formulas from my slide: metres divided by 0.75 for steps, and 0.5 times weight times kilometres for calories. You set your weight on the Account page.
- Optional, if time allows: tap **Start journey** to show time, pace and steps counting.

### 2:30 to 3:00, C: spend coins (Shop page)
- With 70 coins, buy **Free bubble tea** (50 coins). A voucher code like `TH-7KQ2MX` appears.
- Try the **Gold pin** (40 coins) with the 20 left: a notice says you can't afford it.
> Coins turn walking into a real reward. Later this could work with real campus shops.

**End:** C says "Thank you, we're happy to take questions."

---

## If something goes wrong

| Problem | Do this |
|---|---|
| The map is blank | Check the Wi-Fi. The map pictures come from the internet. |
| The route is dashed straight lines | That's our fallback working. Say so: "no routing key here, so Python fell back to straight lines." |
| The browser asks for your location | You're on `?fake=`, so just say no. |
| Coins were already paid before the demo | Delete `instance\geohunt.db`, run `python seed_demo.py`, restart the app, log in again. |
| Anything else breaks | Play the backup screen recording. Record one the day before. |

## Likely questions

| Question | Who | Short answer |
|---|---|---|
| Why is there so little JavaScript? | A | On purpose. Every game rule is Python; JavaScript reads GPS, draws the map and runs the journey timer. That keeps the rules easy to test. |
| Is it really 61% Python? | B | Yes, counted by bytes the way GitHub's language bar does, and that includes our test files. Without the tests, the app code itself is about 4,300 lines of Python next to 7,000 of HTML and CSS. |
| How do you stop cheating with a fake location? | B | Partly. A saved journey that is faster than walking or running is refused (`journey_log.speed_problem`). A single claim still trusts the phone's GPS; `?fake` is only for demos. |
| What happens if the routing API is down? | A | `routing.get_route()` returns straight lines and a warning, and the tests cover that path. |
| How accurate are the calories? | C | It's an estimate: 0.5 × kg × km is a common rule of thumb for walking, not a medical number. |
| How do you work as a team? | B | One branch per feature, a pull request for each, and each file has one owner, so we rarely get merge conflicts. |

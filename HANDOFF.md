# Handoff: login, new look, info board

From A. Everything is on the branch **`feature/distance-by-treasure`** (6 commits on top of `main`, not pushed yet). All 101 tests pass.

## What changed

**1. The map needs a login**
- Opening `/` without being logged in sends you to `/login`. After you log in, you land back on the page you asked for (`/?drag` stays `/?drag`).
- Changed: `app.py` (B), `templates/login.html` (B), `test_api.py` (B). Each change is marked with an `# A:` comment.
- New test file: `test_login_redirect.py`.

**2. Every page has the same look**
- Colours: dark green `#17332d`, with orange `#f2a93b` for highlights.
- Every page has a top bar with links to **Map**, **Hide a treasure** and **Account**.
- New shared files:
  - `static/css/app.css`: the styles for the map, login and upload pages.
  - `templates/_head.html`: fonts, the stylesheet, and the colour of the phone's browser bar.
  - `templates/_topbar.html`: the top bar.
- Use them in a new page like this:
  ```html
  <head>{% include "_head.html" %}<title>…</title></head>
  <body>{% set active = "map" %}{% include "_topbar.html" %} …
  ```
- Login page: shows one form at a time (Log in, or Create an account).
- Upload page: the same card style as the login page.
- C's landing page (`index.html`) is now served at **`/welcome`**:
  - `styles.css` moved from `templates/css/` to `static/css/`. Flask only serves files from `static/`, so it couldn't load from the old place.
  - Its colours were switched from brown and gold to green and orange.
  - Its buttons now lead to the map.

**3. The map page** (`templates/map.html`)
- The base map is colour satellite imagery with street names on top. The layer switcher was removed.
- Treasures are plain pins. The orange pin is the treasure you are hunting; green pins are the others.
- **Tap a pin** and three things happen:
  - The pin grows.
  - An info board slides in from the right with the treasure's name, hint, walking distance and minutes.
  - The route is drawn to that treasure.
- The tapped treasure becomes the one you hunt: its pin turns orange, and the bottom card measures the distance to it.
- Finding a treasure (within 20 m) turns the bottom card orange and shows 🎉.
- Smaller fixes:
  - Drag mode no longer sends dozens of requests per second.
  - Treasure names are shown as plain text, so a name can't inject HTML.

**4. `/api/distance` takes an optional `treasure_id`** (agreed with B)
- `GET /api/distance?lat=..&lon=..&treasure_id=3` measures to treasure 3.
- Without `treasure_id`, it measures to the first treasure, like before.
- A bad id returns 400. An unknown id returns 404.
- Three new tests in `test_api.py`.

**5. Safety**
- `python app.py` no longer turns on debug mode by default. Debug mode lets anyone on the same Wi-Fi run code on your laptop.
- To turn it on for yourself: `$env:FLASK_DEBUG = "1"`.

**Test file:** `test_pages.py` checks that every page loads with the shared style and top bar, and that the map has the info board.

## Set up (once)

In PowerShell:

```powershell
git clone https://github.com/Thang2170/I2P_Final_Project-Geocaching.git
cd I2P_Final_Project-Geocaching
git checkout feature/distance-by-treasure      # until it is merged into main
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

If `activate` is blocked, run this once, then try again:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

**Walking routes (optional).** Without a key the app still works, but routes are dashed straight lines.
1. Get a free key at openrouteservice.org (Dashboard → create token).
2. Save it for your Windows user:
   ```powershell
   [Environment]::SetEnvironmentVariable("ORS_API_KEY", "<your-key>", "User")
   ```
3. Close **all** terminals, including VS Code's, and open a new one.

Never put the key in code, in a chat or in git. Each of us should use our own key, because the free limit is about 2,000 routes per day per key. Phones don't need the key: only the laptop running the server does.

## Run

```powershell
venv\Scripts\activate
python app.py
```

- Open **https://localhost:5000**.
- The browser warns "not secure" because the app makes its own certificate. Click *Advanced → Continue*; on your own laptop that is fine.
- Create an account on the login page. Then you're on the map.

**Test modes** (no walking needed):
- `https://localhost:5000/?drag`: drag the 🚶 marker to pretend you're moving.
- `https://localhost:5000/?fake=24.7960,120.9950`: pretend you're standing at those coordinates.

**Other pages:**
- `/upload`: hide a new treasure.
- `/welcome`: the landing page.

**On a phone** (GPS only works over real HTTPS):
1. Install ngrok, sign up at ngrok.com, and run `ngrok config add-authtoken <token>` once.
2. Start `python app.py`.
3. In a second terminal, run:
   ```powershell
   ngrok http https://localhost:5000
   ```
   Note the `https://` before localhost. Without it, you get error `ERR_NGROK_3004`.
4. Open the `https://….ngrok-free.dev` address it prints on your phone. Tap *Visit Site* once.
5. Press Ctrl+C in the ngrok terminal when you're done, because anyone with the link can open the app while it runs.

**If the page loads forever:** you probably clicked inside the terminal running Flask. Windows pauses a program while you are selecting text in its window. Press **Esc** in that window. Running Flask in VS Code's terminal avoids this.

**Tests:** `python -m unittest -v`. The tests never call the real routing service. Most use a throwaway in-memory database. The ones that load `app.py` (`test_api.py`, `test_pages.py`, `test_login_redirect.py`) read `geohunt.db` but don't change your treasures.

## Still open

**For B**
- `POST /api/treasures` still works without logging in. Should uploading require a login now that the map does?
- `test_api.py` uses the real `geohunt.db`, unlike the other tests, which use an in-memory database. If someone deletes or edits the first treasure, its tests can break.
- `coins.py` is empty.
- For a real deployment, set a `SECRET_KEY` environment variable. The built-in one is for testing only.

**For C**
- `README.md` says the database and routes are "planned", but both work now. Login, upload, `/welcome` and the setup steps above could go there.
- The landing page shows made-up numbers ("3 day streak", "Level 04", "1,280 pts"). Replace or remove them before the demo.
- New pages should use `_head.html` and `_topbar.html` (see section 2).

**For A**
- `crossings.py` is empty.
- `location.is_near()` isn't used anywhere.
- Next task: the "Random route" button (Feature 6).

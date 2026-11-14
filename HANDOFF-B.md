# Handoff from B (Data and Backend): 14 Nov 2026

Everything below is **merged into `main`** (pull requests #26 to #33). All **471 tests pass** on `main`.

## Get up to date (once)

In PowerShell, in the project folder:

```powershell
git checkout main
git pull
venv\Scripts\activate
python -m unittest        # should end with OK (471 tests)
python seed_demo.py       # demo players, treasures, hunts, posts
python app.py
```

- Open **https://localhost:5000**. Demo login: **`demo_player`**, password **`demo1234`**.
- **No need to delete your database.** Every change below adds new tables only, never new columns,
  so your old `instance/geohunt.db` keeps working.
- The first time `demo_player` opens the map, the welcome tour pops up. Tap **Skip** if you don't need it.

## What's new

### 1. Community: a news feed (#26)

**Page:** `/community`, in three columns.
- **Left:** your stats and coins.
- **Middle:** the feed.
- **Right:** Top hunters. On a phone this becomes a strip you swipe sideways.

**What players can do**
- Write a post (up to 500 characters), and delete their own written posts.
- Like a post (tap again to take the like back).
- Comment (up to 300 characters), and delete their own comments.
- Every **finished hunt appears as a post by itself**, with the treasure's name and the walk's numbers.
  Hunt posts can't be deleted.

**Files**
- Rules: `feed_rules.py`
- API: `feed_api.py`
- Page: `templates/community.html`

**New tables:** `posts`, `post_likes`, `post_comments`

### 2. Saving finished hunts (#26)

When you reach a treasure from **Start journey** on the map, the hunt is saved: distance, time, steps and calories.
Python works out the steps and calories; it never trusts the browser for them.

**Files**
- Rules: `journey_log.py`
- API: `journey_api.py`
- Page: the journey panel in `templates/map.html`

**New table:** `journeys` (one per player and treasure)

### 3. First-time tour and "first quests" (#27, #30)

**The tour**
- New players get a 6-slide tour on the map: Welcome, The map, Go and find it, Hide your own, Play together,
  Your first quests.
- It shows once per player.
- **To change the words, edit `TOUR_STEPS` in `onboarding.py`.**

**The quest board** (the last slide)
- 6 first quests that tick themselves off: save your weight, find a treasure, hide one, post on Community,
  join a hunt, buy something.
- The **Quests 0/6** button under the zoom buttons on the map reopens the board at any time.

**Links**
- `/?tour` replays the tour. The Account page and the welcome sidebar link here.
- `/?quests` opens the quest board directly.

**Files**
- Rules: `onboarding.py`
- API: `onboarding_api.py`
- Page: `templates/_tour.html`, added to `map.html` with one line

**New table:** `tour_seen`

### 4. Welcome page clean-up (#28, #29)

- The sidebar has a **Community** link, with a pixel speech-bubble icon (`.px-icon--comment` in `pixel.css`).
- The pixel map preview card ("Open the map") and the "How it works" card were **removed**.
- The sidebar's "New to StepQuest" box now says **Take the tour** (`/?tour`).
- Test: `test_welcome_page.py`

### 5. Group chat for each hunt (#31, #32)

**Pages**
- On `/hunts`, every hunt you're **playing** in has a gold **Open group chat** button.
  The message right after you join has one too.
- The chat page is `/hunts/<id>/chat`:
  - A strip shows who is in the hunt; people waiting in line are faded.
  - Messages are bubbles, up to 300 characters.
  - New messages show up every 4 seconds without reloading.

**Who can chat:** only players who are **playing**.
- People **waiting in line can't chat yet**. They see "You are #n in line…".
- When they move up, the open chat page lets them in by itself.
- Leaving the hunt takes you out of the chat.

**Files**
- Rules: `hunt_chat.py` (`chat_access()`)
- API: `chat_api.py`
- Page: `templates/chat.html`

**New table:** `hunt_messages`

### 6. Player profiles (#33)

**Page:** `/players/<username>`
- Avatar, when they joined, and their Leaderboard rank.
- Stats: coins, found, hidden, hunts walked, km, steps.
- Recent hunts, the treasures they hid, and their recent posts.

**Clicking an avatar or name opens the profile** in these places:
- The chat's people strip and chat messages.
- Community posts, comments and Top hunters.
- The Leaderboard.

**Privacy:** it only shows what is already public on the Leaderboard and the feed. Weight is never shown,
and a test checks this.

**Files**
- Rules: `player_profile.py`
- API: `profile_api.py`
- Page: `templates/profile.html`

**No new tables.**

## API added in this round

All of these need a login: they return **401** when you're logged out.

| Method and path | What it does |
|---|---|
| `GET /api/feed?offset=` | The feed, 20 posts at a time |
| `POST /api/posts` · `DELETE /api/posts/<id>` | Write or delete a post |
| `POST /api/posts/<id>/like` | Like, or take the like back |
| `POST /api/posts/<id>/comments` · `DELETE /api/comments/<id>` | Write or delete a comment |
| `GET /api/onboarding[?again=1]` · `POST /api/onboarding/seen` | The tour and quests, and "seen it" |
| `GET /api/hunts/<id>/messages?after=` · `POST /api/hunts/<id>/messages` | Read or send chat messages |
| `GET /api/players/<username>` | A player's public profile |

## Things that happened that you should know

- **The map picker for Hide a treasure:** #25 (map picker plus photo) and my own version did the same thing.
  We **kept #25** and dropped mine.
- **CSS name clash:** the admin page already used the class `.feed`. The Community feed uses **`.news-feed`**
  instead, so the two don't affect each other.
- **The `feature/community` merge mix-up:** main was merged into that branch twice, once on GitHub and once
  on a laptop. The GitHub merge had lost `journey_api.py` and other files, so we kept the laptop version.
  **Lesson: always `git pull` before you start working on a branch someone else may have touched.**

## For each of you

**A**
- On the Leaderboard page, names are now links to profiles. That's a small change in
  `templates/leaderboard.html`, marked `// B:`.
- If you add a list somewhere else, avoid the class name `.news-feed`.

**C**
- On the welcome page (`index.html`), two cards were removed and the Community link was added.
- The styles for the removed cards (`.map-panel`, `.map-illustration`, `.tip-card` in `styles.css`) aren't used
  any more. You can delete them.
- `README.md` doesn't mention Community, chat, profiles or the tour yet.

**Everyone**
- New pages should use `_head.html` and `_topbar.html`.
- Show players' text with `textContent`, never `innerHTML`.

## Still open

1. **Walking routes:** `routing.py` still calls `api.openrouteservice.org`, which shut down in November 2026,
   so routes fall back to dashed straight lines. It needs to call **`api.heigit.org`** instead, still using
   the `ORS_API_KEY` environment variable. **B will do this next.**
2. **Chat updates:** the chat checks for new messages every 4 seconds. It doesn't push them instantly, but
   that's fine for the demo.
3. **Demo day:** `demo_player` will see the tour on first login. Either show it in the pitch, or log in once
   beforehand and press Skip.

## How we work (reminder)

- **One branch per change**, started from the latest main:
  ```powershell
  git checkout main
  git pull
  git checkout -b <branch>
  ```
- **Before committing,** run `python -m unittest` and `git status`.
- **Add files by name**, not `git add .`.
- **Then:** push, open a pull request, merge.
- **Rules go in plain Python modules** with no Flask and no database. API files stay thin.
- **Add new tables, never new columns.**
- **Write tests** using `create_app("sqlite:///:memory:")`.
- **Never put the routing key in code or chat.** It lives in the environment variable `ORS_API_KEY`.

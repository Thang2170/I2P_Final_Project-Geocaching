# 🗺️ StepQuest
 
**Walk more. Meet People. Win Rewards.**
 
StepQuest is a location-based treasure-hunting web app built with Python and Flask. Players explore the city, walk to hidden treasures, and earn coins when they reach a target location. It combines real-world movement with a simple game loop: discover treasures, complete hunts, hide your own, and climb the leaderboard.
 
It is a mobile-first, geocaching-style game designed for students and local communities who want a fun way to explore their surroundings while completing quests and collecting rewards.
 
---

## Overview
 
StepQuest asks for the player's GPS location, calculates how far they are from each treasure, and checks whether they have reached the hidden destination. When a player gets close enough, the treasure is marked as found and the player receives rewards such as points, coins, or unlockable progression.
 
StepQuest turns everyday walking into an interactive adventure. Players can:
 
- Find hidden treasures on a live map
- Walk to a target using GPS proximity
- Earn coins and climb the leaderboard
- Hide their own treasure for others to discover
- Join hunts and compete with other players
- Track their progress, profile, and rewards
---
 
## Features


### Gameplay
 
| Feature | Description |
| --- | --- |
| **Live map** | Real-time GPS tracking with the player's position and treasure markers, powered by Leaflet and satellite imagery. Treasures you have already found disappear from your map. |
| **Walking routes** | Tap a treasure to see the walking route, distance and minutes, from the HeiGIT openrouteservice API (needs an `ORS_API_KEY`, see below). |
| **Journeys** | Press *Start journey*: time, pace, steps and calories count up as you walk, and the hunt is saved when you arrive. |
| **Distance calculation** | The server computes the distance between the player and each treasure from their coordinates. |
| **Treasure found detection** | A treasure is counted as found once the player is within a set radius of its location. |
| **Coin rewards** | Finding treasures and completing hunts earns coins and progression. |
| **In-app shop** | Spend earned coins on rewards in the shop. |
| **Leaderboard** | See how you rank against other players. |
| **First-time tour** | A short tour for new players and a *first quests* checklist that ticks itself off (the *Quests* button on the map reopens it). |
 
### Social and community
 
| Feature | Description |
| --- | --- |
| **Hunt system** | Join hunts with a waiting line when they are full, and compete with other players. |
| **Group chat** | Every hunt has a chat for the players in it, with an unread count on the Hunts page. People still waiting in line get in when they move up. |
| **Treasure upload** | Hide your own treasure: tap the map to place it, add a hint and a photo. |
| **Community feed** | Posts, likes and comments, plus a post for every finished hunt. |
| **Player profiles** | Tap any avatar or name to see that player's stats, hunts, hidden treasures and posts. |
| **Notifications** | A bell in the top bar: likes and comments on your posts, and when you move up from a waiting line. |
 
### Platform
 
| Feature | Description |
| --- | --- |
| **Login and profiles** | Player accounts; your Account page shows your own profile plus your settings. |
| **Fair play** | A short wait between posts, comments and chat messages stops spamming. Login cookies are signed with a random key kept in `instance/`. |


## Tech stack

| Part | Technology |
| --- | --- |
| Backend | Python 3, Flask |
| Database | SQLite via Flask-SQLAlchemy |
| Map | Leaflet, Esri satellite imagery |
| Routing | HeiGIT openrouteservice (`api.heigit.org`) |
| Frontend | HTML, CSS, a little JavaScript |
| Testing | Python `unittest` |
| Teamwork | Git and GitHub |

## Project overview

| File or folder | What it does |
| --- | --- |
| `app.py` | Creates the Flask app (`create_app()`) and registers one Blueprint per feature |
| `*_api.py` | The Blueprints: thin web routes for each feature (`treasure_api`, `hunt_api`, `feed_api`, `chat_api`, ...) |
| Plain-Python rule files | The game rules, with no Flask or database: `coins.py`, `queue_logic.py`, `feed_rules.py`, `hunt_chat.py`, `onboarding.py`, `notify_rules.py`, `rate_limit.py`, ... |
| `location.py`, `calculator.py`, `routing.py` | Distances, steps and calories, and walking routes |
| `models.py` | The database tables (SQLite through Flask-SQLAlchemy) |
| `demo_content.py`, `demo_data.py`, `seed_demo.py` | Demo players, treasures, hunts, posts and chat (`python seed_demo.py`) |
| `templates/`, `static/css/` | HTML pages and the 8-bit pixel look |
| `tests/` | Automatic tests (run `python -m unittest` from the project folder) |
| `DEMO.md`, `REHEARSAL.md` | The demo story and the rehearsal checklist |

## How the Game Works
 
1. A player opens the app and logs in.
2. The browser requests permission to access GPS location.
3. The server calculates the distance to nearby treasures.
4. The map shows the player's location and the treasure positions.
5. The player walks toward the target, guided by hints and the distance readout.
6. When the player is within range, the treasure is counted as found.
7. Rewards, coins, and progression are updated in the app.
---

## Getting Started
 
### Prerequisites
 
- **Python 3.8 or newer** (with `pip`)
- **Git**
- A modern browser with geolocation support (Chrome, Firefox, Safari, Edge)
### 1. Clone the repository
 
```bash
git clone https://github.com/Thang2170/I2P_Final_Project-Geocaching.git
cd I2P_Final_Project-Geocaching
```
 
### 2. Create a virtual environment
 
**Windows (PowerShell):**
 
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```
 
**macOS / Linux:**
 
```bash
python3 -m venv .venv
source .venv/bin/activate
```
 
### 3. Install dependencies
 
```bash
pip install -r requirements.txt
```
 
### 4. Walking routes (optional)

Without a key the app still works, but routes are dashed straight lines. Get a free key at
**account.heigit.org**, then save it for your Windows user (never put it in code or git):

```powershell
[Environment]::SetEnvironmentVariable("ORS_API_KEY", "<your-key>", "User")
```

Close **all** terminals (also VS Code's) and open a new one.

### 5. Run the app

```bash
python seed_demo.py   # optional: demo players, treasures, hunts, posts and chat
python app.py
```
 
Then open the app in your browser:
 
```text
https://localhost:5000/
```
 
> **Note:** If your browser shows a security warning about the local certificate, accept it to continue. The app uses a development certificate because browsers only allow GPS access on secure (HTTPS) pages.
 
### 6. Run on a phone
 
To test real GPS on a mobile device:
 
1. Connect your phone and your computer to the **same Wi-Fi network**.
2. Find your computer's local IP address.
   - Windows: run `ipconfig` and look for the IPv4 address.
   - macOS / Linux: run `ifconfig` or `ip addr`.
3. Start the app on your computer with `python app.py`.
4. On your phone, open:
```text
https://YOUR_COMPUTER_IP:5000/
```
 
5. Accept the certificate warning and **allow location access** when prompted.
---

The local development certificate is temporary and not trusted by the phone. Continue past the browser's certificate warning, then allow location access. This HTTPS setup is for local testing only; use a trusted certificate or HTTPS hosting for production.


## Roadmap Ideas
 
The modular design makes it straightforward to extend StepQuest with:
 
- Additional hunt modes
- Live chat updates (WebSockets instead of checking every few seconds)
- Push notifications on the phone
---


## Running the tests

```bash
python -m unittest
```

All tests live in `tests/` and use a throwaway in-memory database, so they never touch your own data.

## Team

Built by a team of three students 
- Nguyen Cao Thang
- Le Tran Vinh Hung
- Luong Quoc Bao

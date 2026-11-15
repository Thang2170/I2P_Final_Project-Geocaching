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
| **Live map** | Real-time GPS tracking with the player's position and treasure markers, powered by Leaflet and OpenStreetMap. |
| **Distance calculation** | The server computes the distance between the player and each treasure from their coordinates. |
| **Treasure found detection** | A treasure is counted as found once the player is within a set radius of its location. |
| **Coin rewards** | Finding treasures and completing hunts earns coins and progression. |
| **In-app shop** | Spend earned coins on rewards in the shop. |
| **Leaderboard** | See how you rank against other players. |
 
### Social and community
 
| Feature | Description |
| --- | --- |
| **Hunt system** | Join hunts through queue/join logic and compete with other players. |
| **Treasure upload** | Hide your own treasure and add hints and metadata for others to follow. |
| **Community and journey sections** | Activity feeds showing what players around you are up to. |
 
### Platform
 
| Feature | Description |
| --- | --- |
| **Login and profiles** | Player accounts with a personal profile page. |


## Tech stack

| Part | Technology |
| --- | --- |
| Backend | Python 3, Flask |
| Database | SQLite via Flask-SQLAlchemy |
| Map | Leaflet, OpenStreetMap |
| Frontend | HTML, CSS, a little JavaScript |
| Testing | Python `unittest` |
| Teamwork | Git and GitHub |

## Project overview

| File or folder | What it does |
| --- | --- |
| `app.py` | Flask server and routes (map page, `/api/distance`) |
| `location.py` | Distance between GPS points (`haversine_m`) and the nearness check (`is_near`) |
| `calculator.py` | Steps and calories from distance |
| `models.py` | Database tables for treasures |
| `templates/` | HTML pages, including `map.html` |
| `tests/` | Automatic tests (run `python -m unittest` from the project folder) |

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
 
### 4. Run the app
 
```bash
python app.py
```
 
Then open the app in your browser:
 
```text
https://localhost:5000/
```
 
> **Note:** If your browser shows a security warning about the local certificate, accept it to continue. The app uses a development certificate because browsers only allow GPS access on secure (HTTPS) pages.
 
### 5. Run on a phone
 
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
- Improved routing to treasures
- Richer community features
---


## Team

Built by a team of three students 
- Nguyen Cao Thang
- Le Tran Vinh Hung
- Luong Quoc Bao

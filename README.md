# I2P Final Project Geocaching Treasure Hunt

# Geocaching Treasure Hunt

Geocaching Treasure Hunt is a web app where players hunt for hidden treasures with a map. Players walk to real places, find hidden treasures, and earn coins. The app shows a map with a treasure on it and tells the player how far away they are.

This is the final project for our class (I2P). The app is written mostly in Python (the class requires at least 50% Python).

## Table of contents

1. [Features](#features)
2. [How it works](#how-it-works)
3. [Tech stack](#tech-stack)
4. [Project structure](#project-structure)
5. [Getting started](#getting-started)
6. [Running the tests](#running-the-tests)
7. [API reference](#api-reference)
8. [Calculator formulas](#calculator-formulas)
9. [Team workflow](#team-workflow)
10. [Team and file ownership](#team-and-file-ownership)
11. [Troubleshooting](#troubleshooting)
12. [Known limitations](#known-limitations)
13. [Project timeline](#project-timeline)

## Features

The project is built in small pieces. This table shows what each feature does and where it stands.

| Feature | What it does | Status |
|---|---|---|
| Distance to treasure | Calculates the distance in meters between the player and a treasure | Done |
| "Is the player near?" check | Tells whether the player is within 20 m of a treasure | Done |
| Map page | Shows a Leaflet / OpenStreetMap map with a treasure and the player's position | Done |
| Distance API | The browser sends GPS numbers and Python sends back the distance | Done |
| Steps and calories calculator | Estimates steps and calories burned from a walking distance | In review |
| Home page | A phone-first start page with Start hunt, Upload treasure, and Shop buttons | In review |
| Database for treasures | Stores treasures (name, description, latitude, longitude) | In progress |
| Walking routes and random routes | Suggests walking routes to a treasure | Planned |
| Street crossing warning | Warns the player about street crossings on a route | Planned |
| Coin system | Rewards players with coins for finding treasures | Planned |
| Join-a-hunt list | A queue for players who want to join a hunt | Planned |
| Upload treasure and shop | Players add their own treasures and spend coins | Planned |

## How it works

We follow one rule everywhere:

> The browser only collects raw data (like GPS numbers). Python does the real work and sends back the answer.

For example, when the player opens the map:

1. The browser reads the player's GPS position.
2. The browser sends the numbers to the Flask server at `/api/distance`.
3. Python calculates the distance to the treasure with the haversine formula and sends back the answer.
4. The browser shows the result on the map.

This keeps most of our code in Python.

## Tech stack

- **Python 3** for all logic: distance, calculator, database, routes
- **Flask** for the web server
- **Flask-SQLAlchemy** with **SQLite** for the database (in progress)
- **Leaflet** and **OpenStreetMap** for the map in the browser
- **HTML and CSS** for the pages
- **unittest** (built into Python) for automatic tests
- **Git and GitHub** for teamwork

## Project structure

```
I2P_Final_Project-Geocaching/
├── app.py                 Flask server and its routes
├── location.py            Distance between GPS points, "is the player near" check
├── test_location.py       Automatic tests for location.py
├── calculator.py          Steps and calories from distance
├── test_calculator.py     Automatic tests for calculator.py
├── models.py              Database tables
├── coins.py               Coin system (coming soon)
├── routing.py             Walking and random routes (coming soon)
├── crossings.py           Street crossing warning (coming soon)
├── templates/
│   ├── map.html           Map page (Leaflet + OpenStreetMap)
│   └── home.html          Home page
├── static/
│   └── style.css          Styles for the pages
├── requirements.txt       Python libraries the project needs
├── .gitignore             Files Git should skip (venv, database, etc.)
└── README.md              This file
```

## Getting started

You need about 20 minutes. Do this once on your own laptop.

### 1. Install the tools

- **Python 3** from [python.org](https://www.python.org). On Windows, tick **"Add Python to PATH"** in the installer.
- **Git** from [git-scm.com](https://git-scm.com) (or GitHub Desktop).
- **VS Code** from [code.visualstudio.com](https://code.visualstudio.com), with its **Python** extension.
- A free **GitHub account**. Send your username to the repo owner (Thang) so you can be added as a collaborator, then accept the invitation email.

Check the installs. Each command should print a version number:

```
python --version
git --version
```

On a Mac, `python` may be called `python3`. If so, use `python3` (and `pip3`) everywhere below.

### 2. Download (clone) the project

Open a terminal in VS Code (**Terminal → New Terminal**), go to the folder where you keep your school projects, and run:

```
git clone https://github.com/Thang2170/I2P_Final_Project-Geocaching.git
cd I2P_Final_Project-Geocaching
```

Then choose **File → Open Folder** in VS Code and open that folder. All commands in this README are run inside it.

### 3. Create a virtual environment

A virtual environment is a private box for this project's Python libraries, so they don't mix with other projects.

Create it once:

```
python -m venv venv
```

Turn it on. **Do this every time you open a new terminal:**

```
# Windows (Command Prompt or VS Code terminal)
venv\Scripts\activate

# Mac / Linux
source venv/bin/activate
```

You should see `(venv)` at the start of the terminal line. If you don't, the environment is off and the next steps will not work.

On Windows PowerShell, if it says scripts are disabled, run this once and try again:

```
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

### 4. Install the libraries

```
pip install -r requirements.txt
```

Run this again whenever a teammate says a new library was added.

### 5. Run the app

```
python app.py
```

The terminal stays busy while the server runs. That is normal, so don't close it. You should see lines like:

```
* Serving Flask app 'app'
* Debug mode: on
* Running on http://127.0.0.1:5000
```

Open this link in Chrome or Edge:

```
http://127.0.0.1:5000/?fake=24.7960,120.9950
```

You should see:

- A street map centered on National Tsing Hua University, with a marker and the popup "National Tsing Hua University"
- A blue "You are here" circle close to the marker
- A message saying `You are 78 m from National Tsing Hua University`

The map needs an internet connection because the map pictures load from OpenStreetMap.

To stop the server, click in the terminal and press `Ctrl+C`.

## Running the tests

```
python -m unittest -v
```

This runs all test files (`test_location.py` and `test_calculator.py`). Every test should say `ok`, and the last line should say `OK`. If you see `FAILED` or a long red error, copy the message and ask a teammate.

You can also run one test file on its own:

```
python -m unittest -v test_calculator
```

## API reference

### `GET /`

Shows the map page. Add `?fake=LAT,LON` to pretend you are at those coordinates (see [Known limitations](#known-limitations)).

### `GET /api/distance`

Returns the distance from a GPS position to the treasure.

| Parameter | Meaning |
|---|---|
| `lat` | Latitude of the player |
| `lon` | Longitude of the player |

Example request:

```
http://127.0.0.1:5000/api/distance?lat=24.7960&lon=120.9950
```

Example response:

```json
{"meters": 77.9, "treasure": "National Tsing Hua University"}
```

## Calculator formulas

`calculator.py` turns a walking distance into steps and calories.

| Function | Formula |
|---|---|
| `steps_from_distance(distance_m)` | `distance_m / 0.75`, rounded to a whole number (average step is 0.75 m) |
| `calories_from_distance(distance_m, weight_kg)` | `0.5 × weight_kg × distance in kilometers` |

Examples:

- 750 m is 1000 steps.
- Walking 1 km at 60 kg burns 30 calories.
- Walking 5 km at 70 kg burns 175 calories.

Both functions raise a `ValueError` if a number is negative.

## Team workflow

The rule that keeps the team safe: **nobody types code directly on the `main` branch.** Every task gets its own branch, and finished work goes in through a pull request that a teammate reviews.

- `main` is the clean master copy.
- A **branch** is your own scratch copy where you can make mistakes.
- A **pull request (PR)** asks the team to check your branch and add it to `main`.

### Every time you start a task

```
git checkout main
git pull
git checkout -b your-branch-name
```

Use a short name that says what the task is, for example `calculator` or `home-page`.

### While you work

1. Write your code and save the files.
2. Check nothing is broken: run `python -m unittest -v` and `python app.py`.
3. Save a snapshot (a commit) every time something small works:

   ```
   git status
   git add file1.py file2.py
   git commit -m "Say what you did in plain words"
   ```

   Add files by name instead of `git add .`, so scratch files do not go in by mistake.
4. Upload your branch. The first time:

   ```
   git push -u origin your-branch-name
   ```

   After that, just `git push`.

### When the task is done

1. On GitHub, click **Compare & pull request**.
2. Write 2 or 3 sentences about what you changed and how to test it, then click **Create pull request**.
3. Click **Reviewers** and pick a teammate. The reviewer reads the changes, comments if needed, clicks **Approve**, then **Merge pull request**.
4. Everyone then runs `git checkout main` and `git pull` before starting the next task.

### Team rules

- One task per branch. Keep branches short-lived (a few days at most).
- Only edit the files you own (see below). If you need a change in someone else's file, ask the owner or comment on their pull request.
- Always `git pull` on `main` before you make a new branch.
- Never commit passwords, API keys, or the `venv/` folder.
- If you add a Python library, run `pip freeze > requirements.txt` and commit it so everyone gets it.
- Review each other's pull requests. Reading other people's code is one of the best ways to learn.
- Stuck for more than 30 minutes? Message the group chat with your error text.

## Team and file ownership

Two people editing the same file at the same time causes merge conflicts. Each file has one owner, and only the owner edits it.

| Person | Role | Files |
|---|---|---|
| **A** (Thang) | Location, routing, repo owner | `location.py`, `test_location.py`, `routing.py`, `crossings.py`, `templates/map.html` (until the map is finished) |
| **B** | Server and database | `app.py` (A edits it only to add map routes and tells B), `models.py`, `coins.py`, `queue_logic.py` |
| **C** | Calculator, pages, documents | `calculator.py`, `test_calculator.py`, `templates/` (except `map.html`), `static/style.css`, `README.md` |

`requirements.txt` is edited by whoever adds a library. Everyone writes their own part of the proposal.

## Troubleshooting

Read the last line of the red error message first. It usually names the problem.

| What you see | What it means | Fix |
|---|---|---|
| `python` or `pip` is not recognized | Python is not installed, or not on PATH | Reinstall Python and tick "Add Python to PATH", or try `python3` / `pip3` |
| `ModuleNotFoundError: flask` | The virtual environment is off, or libraries are not installed | Look for `(venv)`. If missing, activate it, then run `pip install -r requirements.txt` |
| `ModuleNotFoundError: location` | You are in the wrong folder | `cd` into the project folder, then run the command again |
| `fatal: not a git repository` | You are not inside the project folder | `cd I2P_Final_Project-Geocaching` first |
| `TemplateNotFound: map.html` | The HTML file is not inside a folder named `templates` | Create a folder named exactly `templates` and move the file in |
| `Address already in use` (common on Mac) | Another program uses port 5000 | Change the last line of `app.py` to `app.run(debug=True, port=5001)` and open port 5001 |
| Gray map with no streets | No internet, or the tile layer code is missing | Check your connection and the `L.tileLayer(...)` block in `map.html` |
| "Finding your location timed out" | Laptops often cannot find their location | Add `?fake=24.7960,120.9950` to the end of the link |
| `unable to auto-detect email address` on commit | Git does not know who you are | Run `git config --global user.name "Your Name"` and `git config --global user.email "you@example.com"` |
| `git push` fails with 403 | Your account is not a collaborator yet | Ask the repo owner to add you, then accept the invitation email |
| `git push` asks for a password and fails | GitHub does not accept account passwords in the terminal | Sign in with the browser popup, or use GitHub Desktop |
| `git pull` says `CONFLICT` | Two people changed the same lines | Don't panic and don't delete anything. Message the repo owner with a screenshot |
| You typed code on `main` by mistake | You forgot to make a branch | Before committing, run `git checkout -b your-branch-name`. Your changes come with you |

Useful habits:

- Run `git status` often. It shows which branch you are on and what changed.
- Save all files before running anything.
- Restart `python app.py` if a change does not show up, and refresh the browser with `Ctrl+Shift+R`.

## Known limitations

- **Laptops often cannot find their own location.** To test without GPS, add `?fake=24.7960,120.9950` to the link. The `?fake=` part pretends you are at those coordinates.
- **The map needs internet**, because the map pictures load from OpenStreetMap.
- **Only one test treasure exists for now** (National Tsing Hua University). Later, `app.py` will read treasures from the database instead of the fake one in the code.
- The three buttons on the home page do not work yet. They will be connected to Flask later.

## Project timeline

| Date | Goal |
|---|---|
| Sat 10/24 | Coding tasks finished: distance and map (done), calculator, home page, `models.py` with the Treasure table |
| Wed 10/28 | Writing finished: tech section, feature list, timeline and roles, user stories |
| Fri 10/30 | Everyone reviews the final proposal and slides, then submit |
| Sat 10/31 | Proposal due |

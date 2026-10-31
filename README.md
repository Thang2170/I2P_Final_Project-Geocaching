# I2P Final Project Geocaching Treasure Hunt

# Geocaching Treasure Hunt 
Geocaching Treasure Hunt is a geocaching-style treasure hunt web app. Players open a map on their phone, see where a hidden treasure is, and walk to it. As they move, the app tells them how far away they are, and when they get within 20 meters, they have found it.

The goal is to turn everyday walking into a small adventure: explore your neighborhood, find treasures other players have hidden, and see how far you walked and how many calories you burned along the way.

## How it works

1. The browser asks for your GPS location.
2. The browser sends the raw latitude and longitude to the server.
3. Python does the real work (distance, "are you near the treasure?", steps, calories) and sends the answer back.
4. The map shows the treasure, your position, and the distance between you.

We follow one design rule everywhere: **the browser only collects raw data, and Python does the work.** This keeps most of the code in Python.

## Features

### Available now

- **Interactive map**: a street map (Leaflet + OpenStreetMap) showing the treasure's location and your own position as a blue "You are here" dot.
- **Live distance to the treasure**: the server calculates the distance in meters between you and the treasure using the haversine formula.
- **"You found it" check**: the app knows when you are within 20 meters of the treasure.
- **Test mode without GPS**: add `?fake=LAT,LON` to the URL to pretend you are at any coordinates, which is handy because laptops often cannot find their own location.
- **Automatic tests** for the distance and nearness functions.

### In progress / planned

- **Treasure database**: treasures stored in a database (name, description, coordinates) instead of one fixed treasure in the code.
- **Walking routes**: walking directions to a treasure, plus random routes for exploring.
- **Street crossing warning**: a safety alert when your route crosses a street.
- **Steps and calories calculator**: estimates how many steps and how many calories you used, based on distance walked and body weight.
- **Coin system**: earn coins for finding treasures.
- **Join a hunt**: a queue/list of hunts players can join.
- **Upload treasure**: let players hide their own treasures for others to find.
- **Shop**: spend the coins you earned.
- **Mobile-first home page**: a simple home page designed for phone screens with three big buttons: *Start hunt*, *Upload treasure* and *Shop*.

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
| `test_location.py`, `test_calculator.py` | Automatic tests |

## Project status

Geocaching Treasure Hunt is a class team project and is still under development. The map, distance calculation and nearness check work today; the database, calculator, home page and the rest of the game features are being added step by step.

## Testing on a phone with GPS

Phone browsers require HTTPS before they allow a web page opened over the local network to use GPS. Connect the phone and computer to the same Wi-Fi, then run:

```powershell
python app.py
```

Find the computer's Wi-Fi IPv4 address with `ipconfig`, then open this address on the phone:

```text
https://COMPUTER_IP:5000/
```

The local development certificate is temporary and not trusted by the phone. Continue past the browser's certificate warning, then allow location access. This HTTPS setup is for local testing only; use a trusted certificate or HTTPS hosting for production.

## Team

Built by a team of three students Nguyen Cao Thang, Le Tran Vinh Hung, Luong Quoc Bao as a class project.

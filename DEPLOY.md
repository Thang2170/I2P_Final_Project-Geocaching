# Putting StepQuest online (PythonAnywhere, free)

When this is done, anyone can open **https://YOUR_USERNAME.pythonanywhere.com** on their phone,
from anywhere, with no laptop running. Everyone shares one database on the server.

About 15–20 minutes. Do the steps in order.

## 0. Before you start (on your laptop)
- Push the latest work to GitHub (the repo must contain everything, including `static/models/`).
- Have your **OpenRouteService key** ready (the same one you use locally).

## 1. Create the account (you do this; Claude doesn't make accounts)
1. Go to https://www.pythonanywhere.com and sign up for a free **Beginner** account.
2. Your site address will be `YOUR_USERNAME.pythonanywhere.com`, so pick the username carefully.

## 2. Get the code onto the server
1. Open **Consoles → Bash**.
2. Run (one line at a time):
   ```bash
   git clone https://github.com/Thang2170/I2P_Final_Project-Geocaching.git
   cd I2P_Final_Project-Geocaching
   git checkout feature/live-players
   ```
   (Or `main`, once everything is merged.) If the repo is private, GitHub will ask for a
   personal access token instead of your password.

## 3. Install the libraries
Still in the Bash console:
```bash
mkvirtualenv stepquest --python=python3.13
pip install -r requirements.txt
```
If `python3.13` isn't offered, use the newest `python3.x` the console lists.

## 4. Make the web app
1. Open the **Web** tab → **Add a new web app** → **Manual configuration** (not "Flask") → pick the same Python version.
2. In **Virtualenv**, enter: `/home/YOUR_USERNAME/.virtualenvs/stepquest`
3. In **Static files**, add one row:
   - URL: `/static/`
   - Directory: `/home/YOUR_USERNAME/I2P_Final_Project-Geocaching/static`
4. Turn on **Force HTTPS** (phones only give GPS and the camera to https sites).

## 5. The start-up (WSGI) file
1. On the Web tab, click the **WSGI configuration file** link.
2. Delete everything in it and paste the contents of `deploy/pythonanywhere_wsgi.py`.
3. Change the three `CHANGE-ME` lines: your username, your ORS key, your admin usernames.
   Keep the key **only here**, never in GitHub.
4. Save, then press the green **Reload** button on the Web tab.

## 6. The database
Pick one:
- **Fresh start with demo data** (recommended for the demo): in the Bash console run
  ```bash
  cd ~/I2P_Final_Project-Geocaching && workon stepquest && python seed_demo.py
  ```
- **Bring your laptop's data**: on the **Files** tab, upload your `instance/geohunt.db` into
  `/home/YOUR_USERNAME/I2P_Final_Project-Geocaching/instance/`, then Reload.

New tables (verified treasures, collectibles, crossings, journeys…) are added automatically the
first time the app starts, so an older database file works too.

## 7. Check it
Open `https://YOUR_USERNAME.pythonanywhere.com` on your phone, log in as `demo_player`
(password in `DEMO.md`), allow location, and walk to a treasure. If something is wrong, the
**Web** tab has an **Error log** link: the last lines say what failed.

## Good to know (free account limits)
- **Outside websites are limited.** Free accounts can only reach websites on PythonAnywhere's
  allow-list. If the routing service or OpenStreetMap (crossings) isn't on it, the app falls back
  by itself: straight-line routes, and only crossings added by hand on the admin map. Hand-added
  crossings and everything else work normally.
- **No local AI there.** Ollama runs on your own PC, not on PythonAnywhere. The health summary
  then uses the plain Python rules (same numbers, simpler wording).
- **Renew every 3 months:** free web apps must be renewed with one click on the Web tab.
- **Updating later:** Bash console → `cd ~/I2P_Final_Project-Geocaching && git pull` → Reload.

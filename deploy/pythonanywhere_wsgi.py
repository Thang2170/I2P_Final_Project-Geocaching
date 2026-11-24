"""The start-up file for PythonAnywhere (copy it into their WSGI file, see DEPLOY.md).

PythonAnywhere runs Flask apps for us: it imports `application` from this file instead
of running `python app.py`. It also gives the site https://, which phones need for GPS
and the camera.

Fill in the three CHANGE-ME lines ON PYTHONANYWHERE ONLY. Never put real keys in this
file in the GitHub repository.
"""

import os
import sys

# CHANGE-ME: your PythonAnywhere username (the project was cloned into your home folder)
PROJECT = "/home/YOUR_USERNAME/I2P_Final_Project-Geocaching"
if PROJECT not in sys.path:
    sys.path.insert(0, PROJECT)

# CHANGE-ME: your HeiGIT/OpenRouteService key (without it, routes are straight lines)
os.environ.setdefault("ORS_API_KEY", "PASTE-YOUR-KEY-HERE")
# CHANGE-ME: who may open /admin (comma-separated usernames)
os.environ.setdefault("ADMIN_USERS", "admin")
# SECRET_KEY: not needed. The app makes a random one and keeps it in instance/secret_key.

from app import app as application  # noqa: E402  (the path above must be set first)

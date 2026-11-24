"""Install StepQuest like an app: the manifest, the service worker and the offline page (owner: B).

- GET /manifest.webmanifest   name, colours and icons, so phones offer "Add to Home screen"
- GET /sw.js                  the service worker (static/js/sw.js). Served from the site's root,
                              because a service worker only controls pages at or below its own address.
- GET /offline                what you see when there is no internet and the page isn't cached
"""

from flask import Blueprint, current_app, jsonify, render_template, send_from_directory

from app_icon import BACKGROUND, SIZES

pwa_api = Blueprint("pwa_api", __name__)

APP_NAME = "StepQuest"
PAPER = "#f1ede0"  # --px-bg, shown while the app starts


def manifest():
    """The web app manifest as a dict (tested on its own)."""
    return {
        "name": f"{APP_NAME}: walk, find treasure",
        "short_name": APP_NAME,
        "description": "A treasure hunt that gets you walking.",
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "orientation": "portrait",
        "background_color": PAPER,
        "theme_color": BACKGROUND,
        "icons": [{"src": f"/static/icons/icon-{size}.png", "sizes": f"{size}x{size}",
                   "type": "image/png", "purpose": "any maskable"} for size in SIZES],
    }


@pwa_api.route("/manifest.webmanifest")
def web_manifest():
    response = jsonify(manifest())
    response.mimetype = "application/manifest+json"
    return response


@pwa_api.route("/sw.js")
def service_worker():
    response = send_from_directory(current_app.static_folder, "js/sw.js", mimetype="text/javascript")
    response.headers["Cache-Control"] = "no-cache"  # a new version is picked up straight away
    response.headers["Service-Worker-Allowed"] = "/"
    return response


@pwa_api.route("/offline")
def offline_page():
    return render_template("offline.html")

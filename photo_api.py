"""A photo of the spot where a treasure is hidden (owner: A).

The picture is saved as a file in the app's instance folder (next to the
database), named after the treasure id, so the database never changes:

    instance/photos/<treasure id>.jpg

Like route_api.py, this lives in its own Blueprint. app.py only needs:

    from photo_api import photo_api
    app.register_blueprint(photo_api)
"""

import os

from flask import Blueprint, current_app, jsonify, request, send_from_directory

from auth_api import current_user
from models import Treasure, db
from photo_input import check_photo

photo_api = Blueprint("photo_api", __name__)

EXTENSIONS = ("jpg", "png", "webp")


def photo_folder():
    """The folder the photos live in, created on first use."""
    folder = os.path.join(current_app.instance_path, "photos")
    os.makedirs(folder, exist_ok=True)
    return folder


def photo_filename(treasure_id):
    """The saved photo's file name for this treasure, or None if it has no photo."""
    for extension in EXTENSIONS:
        name = f"{treasure_id}.{extension}"
        if os.path.exists(os.path.join(photo_folder(), name)):
            return name
    return None


def photo_url(treasure_id):
    """Where the browser can load this treasure's photo, or None."""
    if photo_filename(treasure_id) is None:
        return None
    return f"/api/treasures/{treasure_id}/photo"


@photo_api.route("/api/treasures/<int:treasure_id>/photo", methods=["POST"])
def upload_photo(treasure_id):
    """Attach a photo to a treasure. Send a multipart form with a "photo" file.

    Only the player who hid the treasure can add or replace its photo.
    """
    user = current_user()
    if user is None:
        return jsonify(error="Log in first"), 401

    treasure = db.session.get(Treasure, treasure_id)
    if treasure is None:
        return jsonify(error="No such treasure"), 404
    if treasure.created_by != user.id:
        return jsonify(error="Only the player who hid this treasure can add a photo"), 403

    upload = request.files.get("photo")
    data = upload.read() if upload is not None else b""
    try:
        extension = check_photo(data)
    except ValueError as err:
        return jsonify(error=str(err)), 400

    # One photo per treasure: throw away an older one saved under another extension
    old = photo_filename(treasure_id)
    if old is not None:
        os.remove(os.path.join(photo_folder(), old))
    with open(os.path.join(photo_folder(), f"{treasure_id}.{extension}"), "wb") as file:
        file.write(data)
    return jsonify(treasure_id=treasure_id, photo_url=photo_url(treasure_id)), 201


@photo_api.route("/api/treasures/<int:treasure_id>/photo", methods=["GET"])
def get_photo(treasure_id):
    """Send the treasure's photo, or 404 when it has none."""
    name = photo_filename(treasure_id)
    if name is None:
        return jsonify(error="This treasure has no photo"), 404
    return send_from_directory(photo_folder(), name, max_age=0)

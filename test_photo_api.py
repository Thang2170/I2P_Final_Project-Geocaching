import io
import os
import shutil
import tempfile
import unittest

from flask import Flask

from auth_api import auth_api
from models import db
from photo_api import photo_api
from treasure_api import treasure_api

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20
JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 20


class TestPhotoApi(unittest.TestCase):
    def setUp(self):
        # A throwaway app: in-memory database, and photos go to a temporary folder
        # that is deleted afterwards, so tests never touch instance/photos.
        self.folder = tempfile.mkdtemp()
        self.app = Flask(__name__, instance_path=self.folder)
        self.app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
        self.app.config["SECRET_KEY"] = "test-key"
        db.init_app(self.app)
        for blueprint in (auth_api, treasure_api, photo_api):
            self.app.register_blueprint(blueprint)
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        self.client = self.app.test_client()
        self.client.post("/api/register", json={"username": "bao", "password": "secret1"})
        r = self.client.post("/api/treasures", json={"name": "Library", "lat": 24.79, "lon": 120.99})
        self.treasure_id = r.get_json()["id"]

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
        self.context.pop()
        shutil.rmtree(self.folder, ignore_errors=True)

    def upload(self, data, name="spot.png", treasure_id=None, client=None):
        client = client or self.client
        treasure_id = treasure_id or self.treasure_id
        return client.post(f"/api/treasures/{treasure_id}/photo",
                           data={"photo": (io.BytesIO(data), name)},
                           content_type="multipart/form-data")

    def test_upload_page_has_the_map_picker_and_photo_field(self):
        html = self.client.get("/upload").get_data(as_text=True)
        self.assertIn('id="pickMap"', html)
        self.assertIn('type="file"', html)
        self.assertNotIn('inputmode="decimal"', html)  # no more typing lat/lon

    def test_no_photo_yet_gives_404(self):
        self.assertEqual(self.client.get(f"/api/treasures/{self.treasure_id}/photo").status_code, 404)

    def test_photo_is_saved_and_served(self):
        r = self.upload(PNG)
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.get_json()["photo_url"], f"/api/treasures/{self.treasure_id}/photo")
        self.assertTrue(os.path.exists(os.path.join(self.folder, "photos", f"{self.treasure_id}.png")))

        r = self.client.get(f"/api/treasures/{self.treasure_id}/photo")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data, PNG)
        r.close()

    def test_file_name_is_ignored_only_the_bytes_count(self):
        self.assertEqual(self.upload(JPG, name="picture.png").status_code, 201)
        self.assertTrue(os.path.exists(os.path.join(self.folder, "photos", f"{self.treasure_id}.jpg")))

    def test_new_photo_replaces_the_old_one(self):
        self.upload(JPG)
        self.upload(PNG)
        names = os.listdir(os.path.join(self.folder, "photos"))
        self.assertEqual(names, [f"{self.treasure_id}.png"])

    def test_text_file_is_refused(self):
        r = self.upload(b"just some text", name="notes.txt")
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_missing_file_is_refused(self):
        r = self.client.post(f"/api/treasures/{self.treasure_id}/photo", data={},
                             content_type="multipart/form-data")
        self.assertEqual(r.status_code, 400)

    def test_unknown_treasure_is_404(self):
        self.assertEqual(self.upload(PNG, treasure_id=999).status_code, 404)

    def test_logged_out_is_401(self):
        self.assertEqual(self.upload(PNG, client=self.app.test_client()).status_code, 401)

    def test_only_the_hider_can_add_a_photo(self):
        other = self.app.test_client()
        other.post("/api/register", json={"username": "mei", "password": "secret1"})
        self.assertEqual(self.upload(PNG, client=other).status_code, 403)
        self.assertFalse(os.path.exists(os.path.join(self.folder, "photos", f"{self.treasure_id}.png")))


if __name__ == "__main__":
    unittest.main()

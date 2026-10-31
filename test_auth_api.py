import unittest

from flask import Flask

from auth_api import auth_api
from models import Treasure, User, db
from treasure_api import treasure_api


class TestAuthApi(unittest.TestCase):
    def setUp(self):
        # A throwaway app with an in-memory database, so tests never touch geohunt.db.
        self.app = Flask(__name__)
        self.app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
        self.app.config["SECRET_KEY"] = "test-key"
        db.init_app(self.app)
        self.app.register_blueprint(auth_api)
        self.app.register_blueprint(treasure_api)
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
        self.context.pop()

    def register(self, username="bao", password="secret1", client=None):
        return (client or self.client).post("/api/register",
                                            json={"username": username, "password": password})

    def login(self, username="bao", password="secret1", client=None):
        return (client or self.client).post("/api/login",
                                            json={"username": username, "password": password})

    def test_login_page_loads(self):
        r = self.client.get("/login")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"Log in", r.data)

    def test_register_creates_user_and_logs_in(self):
        r = self.register()
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.get_json()["username"], "bao")
        self.assertNotIn("password", str(r.get_json()).lower())
        self.assertEqual(self.client.get("/api/me").get_json()["username"], "bao")

    def test_password_is_stored_hashed(self):
        self.register()
        user = db.session.query(User).one()
        self.assertNotEqual(user.password_hash, "secret1")
        self.assertNotIn("secret1", user.password_hash)
        self.assertTrue(user.check_password("secret1"))
        self.assertFalse(user.check_password("wrong"))

    def test_duplicate_username_rejected(self):
        self.register()
        r = self.register(password="another1")
        self.assertEqual(r.status_code, 409)
        self.assertEqual(db.session.query(User).count(), 1)

    def test_bad_registration_returns_400(self):
        for fields in [{"username": "ab"}, {"username": "bad name"}, {"password": "123"}]:
            with self.subTest(fields=fields):
                data = {"username": "bao", "password": "secret1"}
                data.update(fields)
                self.assertEqual(self.client.post("/api/register", json=data).status_code, 400)
        self.assertEqual(db.session.query(User).count(), 0)

    def test_login_works_after_logout(self):
        self.register()
        self.client.post("/api/logout")
        self.assertEqual(self.client.get("/api/me").status_code, 401)

        r = self.login()
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.client.get("/api/me").get_json()["username"], "bao")

    def test_wrong_password_and_unknown_user_look_the_same(self):
        self.register()
        wrong_password = self.login(password="nope123", client=self.app.test_client())
        unknown_user = self.login(username="nobody", client=self.app.test_client())
        self.assertEqual(wrong_password.status_code, 401)
        self.assertEqual(unknown_user.status_code, 401)
        self.assertEqual(wrong_password.get_json(), unknown_user.get_json())

    def test_login_without_details_returns_400(self):
        self.assertEqual(self.client.post("/api/login", json={}).status_code, 400)

    def test_me_when_logged_out(self):
        self.assertEqual(self.client.get("/api/me").status_code, 401)

    def test_user_without_password_cannot_log_in(self):
        db.session.add(User(username="old"))
        db.session.commit()
        self.assertEqual(self.login(username="old", password="anything").status_code, 401)

    def test_upload_remembers_who_hid_the_treasure(self):
        self.register()
        self.client.post("/api/treasures", json={"name": "Library", "lat": 24.79, "lon": 120.99})
        treasure = db.session.query(Treasure).one()
        self.assertEqual(treasure.creator.username, "bao")

    def test_upload_still_works_when_logged_out(self):
        r = self.client.post("/api/treasures", json={"name": "Library", "lat": 24.79, "lon": 120.99})
        self.assertEqual(r.status_code, 201)
        self.assertIsNone(db.session.query(Treasure).one().created_by)


if __name__ == "__main__":
    unittest.main()

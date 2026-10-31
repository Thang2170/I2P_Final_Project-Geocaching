import unittest

from flask import Flask
from sqlalchemy.exc import IntegrityError

from models import DEMO_TREASURE, Treasure, User, db, seed_demo_data


class TestModels(unittest.TestCase):
    def setUp(self):
        # A throwaway app with a database that lives only in memory,
        # so the tests never touch the real geohunt.db file.
        self.app = Flask(__name__)
        self.app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
        db.init_app(self.app)
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def count_treasures(self):
        return db.session.query(Treasure).count()

    def test_save_and_read_treasure(self):
        db.session.add(Treasure(name="Library", lat=24.79, lon=120.99))
        db.session.commit()

        saved = db.session.query(Treasure).one()
        self.assertEqual(saved.name, "Library")
        self.assertEqual(saved.lat, 24.79)
        self.assertEqual(saved.description, "")  # default value

    def test_to_dict_has_the_keys_the_map_needs(self):
        treasure = Treasure(name="Library", lat=24.79, lon=120.99)
        db.session.add(treasure)
        db.session.commit()

        data = treasure.to_dict()
        self.assertEqual(data["name"], "Library")
        self.assertEqual(data["lat"], 24.79)
        self.assertEqual(data["lon"], 120.99)
        self.assertIn("id", data)
        self.assertIn("description", data)

    def test_seed_adds_the_demo_treasure(self):
        seed_demo_data()

        self.assertEqual(self.count_treasures(), 1)
        self.assertEqual(db.session.query(Treasure).one().name, DEMO_TREASURE["name"])

    def test_seed_twice_does_not_duplicate(self):
        seed_demo_data()
        seed_demo_data()

        self.assertEqual(self.count_treasures(), 1)

    def test_seed_skips_when_treasures_already_exist(self):
        db.session.add(Treasure(name="Mine", lat=1, lon=1))
        db.session.commit()

        seed_demo_data()

        self.assertEqual(self.count_treasures(), 1)

    def test_latitude_out_of_range_is_rejected(self):
        with self.assertRaises(ValueError):
            Treasure(name="Nowhere", lat=91, lon=0)

    def test_longitude_out_of_range_is_rejected(self):
        with self.assertRaises(ValueError):
            Treasure(name="Nowhere", lat=0, lon=181)

    def test_treasure_needs_a_name(self):
        db.session.add(Treasure(lat=1, lon=1))
        with self.assertRaises(IntegrityError):
            db.session.commit()
        db.session.rollback()

    def test_treasure_remembers_who_uploaded_it(self):
        player = User(username="bao")
        treasure = Treasure(name="Library", lat=24.79, lon=120.99, creator=player)
        db.session.add_all([player, treasure])
        db.session.commit()

        self.assertEqual(treasure.creator.username, "bao")
        self.assertEqual(player.treasures[0].name, "Library")

    def test_usernames_must_be_unique(self):
        db.session.add(User(username="bao"))
        db.session.commit()

        db.session.add(User(username="bao"))
        with self.assertRaises(IntegrityError):
            db.session.commit()
        db.session.rollback()

    def test_password_is_hashed_and_checked(self):
        user = User(username="bao")
        user.set_password("secret1")
        self.assertNotEqual(user.password_hash, "secret1")
        self.assertTrue(user.check_password("secret1"))
        self.assertFalse(user.check_password("Secret1"))

    def test_user_without_password_never_matches(self):
        self.assertFalse(User(username="old").check_password("anything"))

    def test_user_to_dict_hides_the_password(self):
        user = User(username="bao")
        user.set_password("secret1")
        self.assertEqual(user.to_dict(), {"id": None, "username": "bao"})


if __name__ == "__main__":
    unittest.main()

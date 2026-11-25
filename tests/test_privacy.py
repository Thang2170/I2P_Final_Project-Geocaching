"""B: download my data, and delete my band data (privacy.py, privacy_api.py)."""

import json
import unittest
from datetime import date, datetime, timedelta, timezone

from app import create_app
from health_api import HealthDevice, HealthReading, hash_token
from models import CoinTransaction, Journey, Post, SafetyAlert, User, db
from privacy import clean_row, clean_value, confirm_problem, export_filename


class RulesTest(unittest.TestCase):
    def test_values(self):
        self.assertEqual(clean_value(datetime(2026, 11, 26, 8, 0)), "2026-11-26T08:00:00+00:00")
        self.assertEqual(clean_value(date(2026, 11, 26)), "2026-11-26")
        self.assertEqual(clean_value(b"\x89PNG..."), "(a file, 7 bytes)")
        self.assertEqual(clean_value(3.5), 3.5)

    def test_secrets_never_leave(self):
        self.assertNotIn("password_hash", clean_row("users", {"id": 1, "username": "ann", "password_hash": "x"}))
        self.assertNotIn("token_hash", clean_row("health_devices", {"id": 1, "token_hash": "y", "name": "band"}))

    def test_filename(self):
        self.assertEqual(export_filename('ann"; rm', datetime(2026, 11, 26)), "stepquest-ann___rm-2026-11-26.json")

    def test_confirm(self):
        self.assertIsNone(confirm_problem({"confirm": "DELETE"}))
        for bad in (None, {}, {"confirm": "delete"}, {"confirm": "yes"}):
            self.assertIn("Type DELETE", confirm_problem(bad))


class ApiTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app("sqlite:///:memory:")
        self.context = self.app.app_context()
        self.context.push()
        self.client = self.app.test_client()
        self.client.post("/api/register", json={"username": "bob", "password": "secret1"})
        self.bob = db.session.execute(db.select(User).filter_by(username="bob")).scalar_one()
        self.client.post("/api/register", json={"username": "ann", "password": "secret1"})  # logged in as ann
        self.ann = db.session.execute(db.select(User).filter_by(username="ann")).scalar_one()
        for who in (self.ann, self.bob):
            device = HealthDevice(user_id=who.id, name=f"{who.username}'s band", token_hash=hash_token(who.username))
            db.session.add(device)
            db.session.flush()
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            for i in range(10):
                db.session.add(HealthReading(user_id=who.id, device_id=device.id, at=now - timedelta(seconds=5 * i),
                                             hr=120 + i, spo2=97, steps=10))
            db.session.add(SafetyAlert(user_id=who.id, reason="low_spo2", title="Low blood oxygen: 88%"))
            db.session.add(CoinTransaction(user_id=who.id, amount=10, reason="found"))
            db.session.add(Post(user_id=who.id, text=f"{who.username} was here"))
        db.session.add(Journey(user_id=self.ann.id, treasure_id=1, distance_m=500, duration_s=400, steps=600, calories=20))
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
        self.context.pop()

    def count(self, model, who):
        return db.session.execute(db.select(db.func.count()).select_from(model).where(model.user_id == who.id)).scalar()

    def test_must_log_in(self):
        other = self.app.test_client()
        self.assertEqual(other.get("/api/me/export").status_code, 401)
        self.assertEqual(other.post("/api/me/band-data/delete", json={"confirm": "DELETE"}).status_code, 401)

    def test_download(self):
        res = self.client.get("/api/me/export")
        self.assertEqual(res.status_code, 200)
        self.assertIn('attachment; filename="stepquest-ann-', res.headers["Content-Disposition"])
        self.assertEqual(res.headers["Cache-Control"], "no-store")
        data = json.loads(res.get_data(as_text=True))
        tables = data["tables"]
        self.assertEqual(data["player"], "ann")
        self.assertEqual(len(tables["health_readings"]), 10)
        self.assertEqual(tables["users"][0]["username"], "ann")
        for name in ("coin_transactions", "posts", "journeys", "safety_alerts", "health_devices"):
            self.assertIn(name, tables)
        text = res.get_data(as_text=True)
        self.assertNotIn("password_hash", text)
        self.assertNotIn("token_hash", text)
        self.assertNotIn("bob was here", text)           # only ann's own rows
        self.assertNotIn("bob's band", text)
        self.assertTrue(all(r["user_id"] == self.ann.id for r in tables["health_readings"]))

    def test_delete_needs_the_word(self):
        res = self.client.post("/api/me/band-data/delete", json={"confirm": "yes"})
        self.assertEqual(res.status_code, 400)
        self.assertEqual(self.count(HealthReading, self.ann), 10)

    def test_delete_band_data_only_yours_and_only_band_data(self):
        res = self.client.post("/api/me/band-data/delete", json={"confirm": "DELETE"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["deleted"], {"health_readings": 10, "safety_alerts": 1, "health_devices": 1})
        self.assertIn("Deleted 10 band readings, 1 paired band and 1 safety stop.", res.get_json()["message"])
        for model in (HealthReading, SafetyAlert, HealthDevice):
            self.assertEqual(self.count(model, self.ann), 0)
            self.assertGreater(self.count(model, self.bob), 0)      # bob's data is untouched
        self.assertEqual(self.count(CoinTransaction, self.ann), 1)  # coins and hunts are kept
        self.assertEqual(self.count(Journey, self.ann), 1)
        # the band's old token no longer works
        res = self.client.post("/api/health/readings", headers={"Authorization": "Bearer ann"},
                               json={"readings": [{"hr": 80, "spo2": 98, "temp_c": 33}]})
        self.assertEqual(res.status_code, 401)

    def test_health_page_has_the_buttons(self):
        html = self.client.get("/health").get_data(as_text=True)
        for part in ('href="/api/me/export"', 'id="deleteForm"', "/api/me/band-data/delete", "Type <b>DELETE</b>"):
            self.assertIn(part, html)
        self.assertNotIn("innerHTML", html)


if __name__ == "__main__":
    unittest.main()

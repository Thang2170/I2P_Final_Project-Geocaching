import unittest

from app import create_app
from hunt_chat import HISTORY_SIZE
from models import HuntMessage, db


class ChatTestCase(unittest.TestCase):
    def setUp(self):
        # A throwaway in-memory database, so tests never touch geohunt.db.
        self.app = create_app("sqlite:///:memory:")
        self.context = self.app.app_context()
        self.context.push()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
        self.context.pop()

    def player(self, name):
        client = self.app.test_client()
        client.post("/api/register", json={"username": name, "password": "secret1"})
        return client

    def new_hunt(self, client, capacity=5):
        r = client.post("/api/hunts", json={"name": "Night walk", "capacity": capacity})
        self.assertEqual(r.status_code, 201)
        return r.get_json()["id"]

    def send(self, client, hunt_id, text="hi"):
        return client.post(f"/api/hunts/{hunt_id}/messages", json={"text": text})

    def read(self, client, hunt_id, after=""):
        return client.get(f"/api/hunts/{hunt_id}/messages?after={after}")


class TestChatApi(ChatTestCase):
    def test_needs_a_login(self):
        guest = self.app.test_client()
        hid = self.new_hunt(self.player("ann"))
        self.assertEqual(self.read(guest, hid).status_code, 401)
        self.assertEqual(self.send(guest, hid).status_code, 401)

    def test_unknown_hunt(self):
        ann = self.player("ann")
        self.assertEqual(self.read(ann, 999).status_code, 404)
        self.assertEqual(self.send(ann, 999).status_code, 404)

    def test_only_people_in_the_hunt_can_read_or_write(self):
        hid = self.new_hunt(self.player("ann"))
        outsider = self.player("bob")
        self.assertEqual(self.read(outsider, hid).status_code, 403)
        self.assertEqual(self.send(outsider, hid).status_code, 403)
        self.assertEqual(db.session.query(HuntMessage).count(), 0)

    def test_send_and_read(self):
        ann, bob = self.player("ann"), self.player("bob")
        hid = self.new_hunt(ann)
        bob.post(f"/api/hunts/{hid}/join")
        r = self.send(ann, hid, "  Meet at the gate  ")
        self.assertEqual(r.status_code, 201)
        self.assertEqual((r.get_json()["text"], r.get_json()["mine"]), ("Meet at the gate", True))
        self.send(bob, hid, "On my way")
        data = self.read(bob, hid).get_json()
        self.assertEqual(data["hunt"]["name"], "Night walk")
        self.assertEqual([(m["author"], m["text"], m["mine"]) for m in data["messages"]],
                         [("ann", "Meet at the gate", False), ("bob", "On my way", True)])
        self.assertEqual([p["username"] for p in data["members"]], ["ann", "bob"])

    def test_after_gives_only_newer_messages(self):
        ann = self.player("ann")
        hid = self.new_hunt(ann)
        first = self.send(ann, hid, "one").get_json()["id"]
        self.send(ann, hid, "two")
        self.assertEqual([m["text"] for m in self.read(ann, hid, first).get_json()["messages"]], ["two"])

    def test_opening_shows_the_newest_messages_oldest_first(self):
        ann = self.player("ann")
        hid = self.new_hunt(ann)
        for n in range(HISTORY_SIZE + 5):
            db.session.add(HuntMessage(hunt_id=hid, user_id=1, text=f"m{n}"))
        db.session.commit()
        texts = [m["text"] for m in self.read(ann, hid).get_json()["messages"]]
        self.assertEqual(len(texts), HISTORY_SIZE)
        self.assertEqual((texts[0], texts[-1]), ("m5", f"m{HISTORY_SIZE + 4}"))

    def test_bad_message_or_after(self):
        ann = self.player("ann")
        hid = self.new_hunt(ann)
        self.assertEqual(self.send(ann, hid, "").status_code, 400)
        self.assertEqual(self.send(ann, hid, "a" * 301).status_code, 400)
        self.assertEqual(self.read(ann, hid, "-2").status_code, 400)

    def test_players_waiting_in_line_can_chat_too(self):
        ann, bob = self.player("ann"), self.player("bob")
        hid = self.new_hunt(ann, capacity=1)
        bob.post(f"/api/hunts/{hid}/join")  # the hunt is full, so bob waits
        self.assertEqual(self.send(bob, hid, "I'm in line").status_code, 201)
        data = self.read(bob, hid).get_json()
        self.assertEqual(data["me"]["status"], {"state": "waiting", "position": 1})
        self.assertEqual([p["state"] for p in data["members"]], ["playing", "waiting"])

    def test_leaving_the_hunt_closes_the_chat(self):
        ann, bob = self.player("ann"), self.player("bob")
        hid = self.new_hunt(ann)
        bob.post(f"/api/hunts/{hid}/join")
        bob.post(f"/api/hunts/{hid}/leave")
        self.assertEqual(self.read(bob, hid).status_code, 403)

    def test_each_hunt_has_its_own_chat(self):
        ann = self.player("ann")
        one, two = self.new_hunt(ann), self.new_hunt(ann)
        self.send(ann, one, "only in one")
        self.assertEqual(self.read(ann, two).get_json()["messages"], [])

    def test_text_is_stored_as_typed_not_as_html(self):
        ann = self.player("ann")
        hid = self.new_hunt(ann)
        self.assertEqual(self.send(ann, hid, "<b>hi</b>").get_json()["text"], "<b>hi</b>")


class TestChatPages(ChatTestCase):
    def test_the_chat_page(self):
        hid = self.new_hunt(self.player("ann"))
        html = self.app.test_client().get(f"/hunts/{hid}/chat").get_data(as_text=True)
        for part in ('id="messages"', 'id="composer"', 'id="members"', "/api/hunts/", "setInterval"):
            with self.subTest(part=part):
                self.assertIn(part, html)
        self.assertNotIn(".innerHTML", html)

    def test_unknown_hunt_page_is_404(self):
        self.assertEqual(self.app.test_client().get("/hunts/999/chat").status_code, 404)

    def test_the_hunts_page_has_the_chat_button(self):
        html = self.app.test_client().get("/hunts").get_data(as_text=True)
        self.assertIn("Open group chat", html)
        self.assertIn("/chat`", html)

    def test_css_styles_the_chat(self):
        css = self.app.test_client().get("/static/css/app.css").get_data(as_text=True)
        for rule in (".chat__messages", ".msg--mine", ".chat__composer"):
            with self.subTest(rule=rule):
                self.assertIn(rule, css)


if __name__ == "__main__":
    unittest.main()

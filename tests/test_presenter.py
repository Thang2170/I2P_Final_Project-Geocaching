"""B: presenter mode (presenter.py, presenter_api.py, _presenter.html)."""

import unittest

from app import create_app
from demo_data import seed_demo_story
from models import db
from presenter import (BACK, END_PAGE, NEXT, START, STEPS, STOP, move, page_after, panel, parse_action,
                       run_sheet, who_talks, who_text)


class PresenterRulesTest(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(parse_action({"action": "next"}), NEXT)
        for bad in ({}, {"action": "jump"}, None):
            with self.assertRaises(ValueError):
                parse_action(bad)

    def test_moving(self):
        last = len(STEPS) - 1
        self.assertEqual(move(None, START), 0)
        self.assertEqual(move(3, START), 0)
        self.assertEqual(move(0, NEXT), 1)
        self.assertIsNone(move(last, NEXT))  # past the last step: finished
        self.assertEqual(move(0, BACK), 0)
        self.assertEqual(move(4, BACK), 3)
        self.assertIsNone(move(4, STOP))
        self.assertIsNone(move(None, NEXT))  # not presenting: nothing to move

    def test_panel(self):
        first, last = panel(0), panel(len(STEPS) - 1)
        self.assertEqual((first["number"], first["total"]), (1, len(STEPS)))
        self.assertTrue(first["first"])
        self.assertEqual(first["next_label"], f"Next: {STEPS[1]['title']}")
        self.assertEqual(last["next_label"], "Finish")
        self.assertIsNone(panel(None))
        self.assertIsNone(panel(len(STEPS)))
        self.assertEqual(page_after(None), END_PAGE)

    def test_the_run_sheet_is_well_formed(self):
        self.assertEqual(len({s["id"] for s in STEPS}), len(STEPS))
        for step in STEPS:
            self.assertIn(step["who"], ("A", "B", "C"))
            self.assertTrue(1 <= len(step["say"]) <= 3, step["id"])
            self.assertTrue(step["page"].startswith("/"))
        self.assertEqual(sum(who_talks().values()), len(STEPS))
        self.assertEqual(set(who_talks()), {"A", "B", "C"})  # everyone talks
        self.assertIn("A presents", who_text())
        self.assertEqual(len(run_sheet()), len(STEPS))


class PresenterApiTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app("sqlite:///:memory:")
        self.ctx = self.app.app_context()
        self.ctx.push()
        seed_demo_story()
        self.c = self.app.test_client()
        self.c.post("/api/login", json={"username": "demo_player", "password": "demo1234"})

    def tearDown(self):
        db.session.remove()
        self.ctx.pop()

    def act(self, action):
        return self.c.post("/api/present", json={"action": action})

    def test_start_next_back_stop(self):
        self.assertEqual(self.act("jump").status_code, 400)
        data = self.act("start").get_json()
        self.assertEqual((data["step"]["number"], data["url"]), (1, STEPS[0]["page"]))
        self.assertEqual(self.act("next").get_json()["url"], STEPS[1]["page"])
        self.assertEqual(self.act("back").get_json()["step"]["number"], 1)
        data = self.act("stop").get_json()
        self.assertIsNone(data["step"])
        self.assertEqual(data["url"], END_PAGE)
        self.assertNotIn('id="presenter"', self.c.get("/shop").get_data(as_text=True))

    def test_the_panel_follows_you_to_every_page(self):
        self.assertNotIn('id="presenter"', self.c.get("/shop").get_data(as_text=True))
        self.act("start")
        for _ in range(3):
            self.act("next")
        html = self.c.get("/shop").get_data(as_text=True)
        self.assertIn('id="presenter"', html)
        self.assertIn(STEPS[3]["title"], html)
        self.assertIn(f"4/{len(STEPS)}", html)

    def test_finishing(self):
        self.act("start")
        for _ in range(len(STEPS) - 1):
            self.act("next")
        self.assertEqual(self.act("next").get_json()["url"], END_PAGE)
        self.assertIn("That was the last step", self.c.get(END_PAGE).get_data(as_text=True))

    def test_the_start_page_lists_every_step(self):
        html = self.c.get("/present").get_data(as_text=True)
        for step in STEPS:
            self.assertIn(step["title"], html)
        self.assertNotIn("innerHTML", html)

    def test_every_step_page_exists_and_has_what_it_points_at(self):
        for step in STEPS:
            res = self.c.get(step["page"], follow_redirects=True)
            self.assertEqual(res.status_code, 200, step["page"])
            look = step["look"]
            if look:
                self.assertTrue(look.startswith("#"), look)
                self.assertIn(f'id="{look[1:]}"', res.get_data(as_text=True), step["id"])


if __name__ == "__main__":
    unittest.main()

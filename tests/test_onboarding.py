import unittest

from coins import COINS_PER_FIND
from location import FOUND_RADIUS_M
from onboarding import FIRST_QUESTS, TOUR_STEPS, parse_ending, quest_list, should_show


class TestTourSteps(unittest.TestCase):
    def test_every_step_has_a_title_text_and_known_picture(self):
        for step in TOUR_STEPS:
            with self.subTest(step=step["id"]):
                self.assertTrue(step["title"])
                self.assertTrue(step["text"])
                self.assertIn(step["sprite"], ("hero", "chest", "coin", "tree", "sparkle"))

    def test_ids_are_unique(self):
        ids = [s["id"] for s in TOUR_STEPS]
        self.assertEqual(len(ids), len(set(ids)))

    def test_the_numbers_match_the_real_rules(self):
        journey = next(s for s in TOUR_STEPS if s["id"] == "journey")["text"]
        self.assertIn(f"{FOUND_RADIUS_M} m", journey)
        self.assertIn(f"+{COINS_PER_FIND} coins", journey)

    def test_the_last_step_is_the_checklist(self):
        self.assertEqual(TOUR_STEPS[-1]["id"], "quests")

    def test_quest_links_are_pages_of_the_app(self):
        for qid, text, link in FIRST_QUESTS:
            with self.subTest(quest=qid):
                self.assertTrue(link.startswith("/") and not link.startswith("//"))


class TestRules(unittest.TestCase):
    def test_new_players_see_the_tour(self):
        self.assertTrue(should_show(already_seen=False))

    def test_it_does_not_come_back_by_itself(self):
        self.assertFalse(should_show(already_seen=True))

    def test_replay_shows_it_again(self):
        self.assertTrue(should_show(already_seen=True, asked_again=True))

    def test_parse_ending(self):
        self.assertEqual(parse_ending({"how": "finished"}), "finished")
        self.assertEqual(parse_ending({"how": "skipped"}), "skipped")
        for data in ({"how": "maybe"}, {}, None, "finished"):
            with self.subTest(data=data), self.assertRaises(ValueError):
                parse_ending(data)


class TestQuestList(unittest.TestCase):
    def test_nothing_done(self):
        quests = quest_list(set())
        self.assertEqual((quests["done"], quests["total"], quests["all_done"]), (0, len(FIRST_QUESTS), False))
        self.assertFalse(any(q["done"] for q in quests["items"]))

    def test_some_done_keeps_the_order(self):
        quests = quest_list({"hide", "find"})
        self.assertEqual([q["id"] for q in quests["items"]], [qid for qid, _, _ in FIRST_QUESTS])
        self.assertEqual(quests["done"], 2)

    def test_all_done(self):
        self.assertTrue(quest_list({qid for qid, _, _ in FIRST_QUESTS})["all_done"])


if __name__ == "__main__":
    unittest.main()

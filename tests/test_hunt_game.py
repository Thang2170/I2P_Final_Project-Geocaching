import unittest

from hunt_game import (FINISHED, OPEN, STARTED, game_state, join_problem, start_problem,
                       win_problem)


class TestGameState(unittest.TestCase):
    def test_states(self):
        self.assertEqual(game_state(None, None), OPEN)
        self.assertEqual(game_state("some time", None), STARTED)
        self.assertEqual(game_state("some time", 7), FINISHED)


class TestStartRules(unittest.TestCase):
    def test_creator_can_start_even_if_the_hunt_is_not_full(self):
        self.assertIsNone(start_problem(user_id=1, creator_id=1, is_playing=True, state=OPEN))

    def test_only_the_creator_can_start(self):
        self.assertIn("Only the player", start_problem(2, 1, True, OPEN))

    def test_any_playing_member_can_start_a_demo_hunt(self):
        self.assertIsNone(start_problem(5, None, True, OPEN))  # demo hunts have no creator

    def test_must_be_playing_not_waiting(self):
        self.assertIn("Join the hunt", start_problem(5, None, False, OPEN))

    def test_cannot_start_twice(self):
        self.assertIn("already started", start_problem(1, 1, True, STARTED))
        self.assertIn("already started", start_problem(1, 1, True, FINISHED))


class TestJoinAndWinRules(unittest.TestCase):
    def test_join_only_while_open(self):
        self.assertIsNone(join_problem(OPEN))
        self.assertIsNotNone(join_problem(STARTED))
        self.assertIsNotNone(join_problem(FINISHED))

    def test_win_when_close_while_racing(self):
        self.assertIsNone(win_problem(STARTED, True, 5))
        self.assertIsNone(win_problem(STARTED, True, 20))  # 20 m still counts, like finding a treasure

    def test_cannot_win_too_far_away(self):
        self.assertIn("173 m away", win_problem(STARTED, True, 173.4))

    def test_cannot_win_before_the_start_or_after_the_end(self):
        self.assertIn("not started", win_problem(OPEN, True, 5))
        self.assertIn("already won", win_problem(FINISHED, True, 5))

    def test_waiting_line_cannot_win(self):
        self.assertIn("waiting line", win_problem(STARTED, False, 5))


if __name__ == "__main__":
    unittest.main()

import unittest

from queue_logic import PLAYING, WAITING, count_players, queue_status


class TestCountPlayers(unittest.TestCase):
    def test_empty_hunt(self):
        self.assertEqual(count_players(0, 5), (0, 0))

    def test_not_full(self):
        self.assertEqual(count_players(3, 5), (3, 0))

    def test_exactly_full(self):
        self.assertEqual(count_players(5, 5), (5, 0))

    def test_extra_players_wait(self):
        self.assertEqual(count_players(8, 5), (5, 3))

    def test_capacity_of_one(self):
        self.assertEqual(count_players(4, 1), (1, 3))


class TestQueueStatus(unittest.TestCase):
    MEMBERS = [10, 11, 12, 13, 14]  # in the order they joined

    def test_not_in_the_hunt(self):
        self.assertIsNone(queue_status(99, self.MEMBERS, 3))
        self.assertIsNone(queue_status(1, [], 3))

    def test_first_player_is_playing_at_position_one(self):
        self.assertEqual(queue_status(10, self.MEMBERS, 3), {"state": PLAYING, "position": 1})

    def test_last_place_is_still_playing(self):
        self.assertEqual(queue_status(12, self.MEMBERS, 3), {"state": PLAYING, "position": 3})

    def test_first_in_line_waits_at_position_one(self):
        self.assertEqual(queue_status(13, self.MEMBERS, 3), {"state": WAITING, "position": 1})

    def test_second_in_line(self):
        self.assertEqual(queue_status(14, self.MEMBERS, 3), {"state": WAITING, "position": 2})

    def test_everyone_plays_when_there_is_room(self):
        for user_id in self.MEMBERS:
            self.assertEqual(queue_status(user_id, self.MEMBERS, 10)["state"], PLAYING)

    def test_leaving_moves_the_next_player_up(self):
        before = queue_status(13, self.MEMBERS, 3)
        after = queue_status(13, [10, 12, 13, 14], 3)  # 11 left
        self.assertEqual(before["state"], WAITING)
        self.assertEqual(after, {"state": PLAYING, "position": 3})


if __name__ == "__main__":
    unittest.main()

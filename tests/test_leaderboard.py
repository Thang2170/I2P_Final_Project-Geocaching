import unittest

from leaderboard import rank_players


def player(username, coins, found=0, hidden=0):
    return {"username": username, "coins": coins, "found": found, "hidden": hidden}


class TestRankPlayers(unittest.TestCase):
    def test_most_coins_first_with_ranks_from_1(self):
        ranked = rank_players([player("ben", 10), player("alice", 60), player("mei", 30)])
        self.assertEqual([p["username"] for p in ranked], ["alice", "mei", "ben"])
        self.assertEqual([p["rank"] for p in ranked], [1, 2, 3])

    def test_same_coins_more_finds_wins_then_name(self):
        ranked = rank_players([player("zed", 20, found=1), player("amy", 20, found=2), player("Bob", 20, found=1)])
        self.assertEqual([p["username"] for p in ranked], ["amy", "Bob", "zed"])

    def test_limit_cuts_the_list(self):
        ranked = rank_players([player(f"p{i}", i) for i in range(30)], limit=5)
        self.assertEqual(len(ranked), 5)
        self.assertEqual(ranked[0]["username"], "p29")

    def test_empty_list_stays_empty(self):
        self.assertEqual(rank_players([]), [])

    def test_input_is_not_changed(self):
        players = [player("ben", 10), player("alice", 60)]
        rank_players(players)
        self.assertEqual(players[0]["username"], "ben")
        self.assertNotIn("rank", players[0])


if __name__ == "__main__":
    unittest.main()

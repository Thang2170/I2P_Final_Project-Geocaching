"""B: the rules of the six new ways to play (box_code, wanderer, ghost, team_lock, travelers, guide)."""

import os
import sys
import unittest
from datetime import datetime, timedelta

import box_code
import ghost
import guide
import team_lock
import travelers as tr
import wanderer
from location import FOUND_RADIUS_M, haversine_m

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "esp32"))
import box_math  # noqa: E402  (the ESP32's copy of the maths)

RFC_KEY = b"12345678901234567890"
RFC_CODES = ("755224", "287082", "359152", "969429", "338314", "254676", "287922", "162583", "399871", "520489")


class BoxCodeTest(unittest.TestCase):
    def test_rfc_4226_codes(self):
        for counter, code in enumerate(RFC_CODES):
            self.assertEqual(box_code.hotp(RFC_KEY, counter), code)
            self.assertEqual(box_math.hotp(RFC_KEY, counter), code)  # the box gets the same

    def test_box_and_server_agree(self):
        secret = box_code.new_secret()
        self.assertEqual(len(secret), 40)
        for t in (0, 29, 30, 1_795_716_000, 2_000_000_017):
            self.assertEqual(box_code.code_at(secret, t), box_math.code_at(secret, t))
            self.assertEqual(box_code.seconds_left(t), box_math.seconds_left(t))

    def test_tidy(self):
        self.assertEqual(box_code.tidy_code(" 123 456 "), "123456")
        self.assertEqual(box_code.tidy_code("123-456"), "123456")
        for bad in ("12345", "1234567", "12a456", "", None, "١٢٣٤٥٦"):
            with self.assertRaises(ValueError):
                box_code.tidy_code(bad)

    def test_check(self):
        secret, now = box_code.new_secret(), 1_795_716_015
        right = box_code.code_at(secret, now)
        self.assertEqual(box_code.check_code(secret, right, now), (box_code.counter_at(now), None))
        self.assertIsNone(box_code.check_code(secret, right, now + 30)[1])   # one slot late is fine
        self.assertEqual(box_code.check_code(secret, right, now + 90)[1], box_code.WRONG_CODE)  # too late
        wrong = str((int(right) + 1) % 1_000_000).zfill(6)
        self.assertEqual(box_code.check_code(secret, wrong, now)[1], box_code.WRONG_CODE)
        self.assertEqual(box_code.check_code(secret, "abc", now)[1], box_code.BAD_CODE)
        used = {box_code.counter_at(now)}
        self.assertEqual(box_code.check_code(secret, right, now, used)[1], box_code.CODE_USED)


class WandererTest(unittest.TestCase):
    SEED, NOW = 1234, 1_795_716_000

    def test_same_seed_same_walk_and_secret_seed_differs(self):
        self.assertEqual(wanderer.position_at(self.NOW, self.SEED), wanderer.position_at(self.NOW, self.SEED))
        self.assertNotEqual(wanderer.position_at(self.NOW, self.SEED), wanderer.position_at(self.NOW, 99))

    def test_stays_on_campus_and_moves_several_hundred_metres_a_day(self):
        for hour in range(0, 24 * 14, 5):
            lat, lon = wanderer.position_at(self.NOW + hour * 3600, self.SEED)
            self.assertLessEqual(haversine_m(lat, lon, *wanderer.HOME), wanderer.RADIUS_M + 1)
        walked = [wanderer.metres_per_day(self.NOW + d * 86400, self.SEED) for d in range(7)]
        self.assertTrue(all(200 < m < 2000 for m in walked), walked)

    def test_the_newest_footprint_is_not_close_enough_to_catch_it(self):
        far = 0
        for hour in range(0, 24 * 7, 7):
            now = self.NOW + hour * 3600
            newest = wanderer.footprints(now, self.SEED)[-1]
            here = wanderer.position_at(now, self.SEED)
            far += haversine_m(newest["lat"], newest["lon"], *here) > wanderer.CATCH_RADIUS_M
        self.assertGreater(far, 20)  # out of 24 samples: you must guess where it went

    def test_footprints_are_old_and_move_in_steps(self):
        marks = wanderer.footprints(self.NOW, self.SEED)
        self.assertEqual([m["hours_ago"] for m in marks], [24, 12, 6, 3])
        self.assertEqual(marks[-1]["label"], "3 hours ago")
        self.assertEqual(wanderer.age_label(1), "1 hour ago")
        self.assertEqual(marks[0]["label"], "yesterday")
        self.assertEqual(marks, wanderer.footprints(self.NOW + 599 - self.NOW % 600, self.SEED))  # same 10 minutes
        now_lat, now_lon = wanderer.position_at(self.NOW, self.SEED)
        self.assertNotIn((round(now_lat, 6), round(now_lon, 6)), [(m["lat"], m["lon"]) for m in marks])

    def test_catching(self):
        lat, lon = wanderer.position_at(self.NOW, self.SEED)
        self.assertEqual(wanderer.try_catch(lat, lon, self.NOW, self.SEED)[0], wanderer.CAUGHT)
        self.assertEqual(wanderer.try_catch(lat + 0.0006, lon, self.NOW, self.SEED)[0], wanderer.CLOSE)   # ~67 m
        self.assertEqual(wanderer.try_catch(lat + 0.0018, lon, self.NOW, self.SEED)[0], wanderer.WARM)    # ~200 m
        self.assertEqual(wanderer.try_catch(lat + 0.01, lon, self.NOW, self.SEED)[0], wanderer.COLD)


T0 = datetime(2026, 11, 20, 8, 0, 0)
POND = (24.7950, 120.9950)


class GhostTest(unittest.TestCase):
    def setUp(self):
        points = [(T0 + timedelta(seconds=s), 24.7950 + (100 - s) * 0.00001, 120.9950) for s in (40, 0, 20)]
        self.path = ghost.ghost_path(T0, T0 + timedelta(seconds=100), points, POND)

    def test_path_is_sorted_and_ends_at_the_treasure(self):
        self.assertEqual([p[0] for p in self.path], [0, 20, 40, 100])
        self.assertEqual(self.path[-1][1:], POND)

    def test_position_between_points(self):
        self.assertEqual(ghost.position_at(self.path, -5), self.path[0][1:])
        lat, _ = ghost.position_at(self.path, 10)
        self.assertAlmostEqual(lat, 24.7950 + 90 * 0.00001)
        self.assertEqual(ghost.position_at(self.path, 500), POND)

    def test_fastest(self):
        self.assertEqual(ghost.fastest([("ann", 90, []), ("ben", 70, []), ("cy", 70, [])])[0], "ben")
        self.assertIsNone(ghost.fastest([]))

    def test_texts(self):
        self.assertIn("Neck and neck", ghost.lead_text(100, 105, "ben"))
        self.assertEqual(ghost.lead_text(50, 90, "ben"), "You are 40 m ahead of ben's ghost.")
        self.assertIn("ghost is 40 m ahead", ghost.lead_text(90, 50, "ben"))
        self.assertIn("You beat ben's ghost by 0:12", ghost.finish_text(88, 100, "ben"))
        self.assertIn("ghost won by 0:20", ghost.finish_text(120, 100, "ben"))

    def test_compare(self):
        start = self.path[0]
        far = ghost.compare(self.path, "ben", 0, start[1] + 0.001, start[2], POND)  # further away than the ghost
        self.assertLess(far["lead_m"], 0)
        self.assertFalse(far["finished"])
        done = ghost.compare(self.path, "ben", 80, POND[0], POND[1], POND)
        self.assertTrue(done["finished"])
        self.assertIn("You beat", done["text"])
        late = ghost.compare(self.path, "ben", 150, start[1], start[2], POND)
        self.assertTrue(late["ghost"]["finished"])
        self.assertIn("got there in 1:40", late["text"])


class TeamLockTest(unittest.TestCase):
    def test_need(self):
        self.assertEqual(team_lock.parse_need("3"), 3)
        self.assertEqual(team_lock.parse_need(2), 2)
        for bad in (1, 4, "x", None, True, 2.5, ""):
            with self.assertRaises(ValueError):
                team_lock.parse_need(bad)

    def test_who_is_here(self):
        now = T0 + timedelta(seconds=100)
        checkins = [(1, T0 + timedelta(seconds=30)), (2, T0 + timedelta(seconds=90)), (3, T0 + timedelta(seconds=50))]
        self.assertEqual(team_lock.here_now(checkins, now), {2, 3})  # 1 tapped 70 s ago: too long

    def test_opens_for_everyone_here_once(self):
        self.assertEqual(team_lock.who_opens(3, {1, 2}, set()), set())
        self.assertEqual(team_lock.who_opens(2, {1, 2}, set()), {1, 2})
        self.assertEqual(team_lock.who_opens(2, {1, 2, 3}, {1, 2}), {3})

    def test_texts(self):
        self.assertIn("1 of 3 here. 2 more players", team_lock.status_text(3, 1, False))
        self.assertIn("1 more player ", team_lock.status_text(2, 1, False))
        self.assertIn("Open!", team_lock.status_text(2, 0, True))
        self.assertIn("3 players", team_lock.claim_refusal_text(3))


class TravelersTest(unittest.TestCase):
    MOVES = [(tr.RELEASE, 1, 10), (tr.PICK, 2, 10), (tr.DROP, 2, 20), (tr.PICK, 3, 20)]

    def test_parse(self):
        self.assertEqual(tr.parse_traveler({"name": "  Golden   Duck "}, {10}), ("Golden Duck", None))
        self.assertEqual(tr.parse_traveler({"name": "Duck", "goal_treasure_id": 10}, {10}), ("Duck", 10))
        for bad in ({"name": "ab"}, {"name": "x" * 31}, {"name": "Duck", "goal_treasure_id": 99},
                    {"name": "Duck", "goal_treasure_id": "10"}, {"name": "Duck", "goal_treasure_id": True}, None):
            with self.assertRaises(ValueError):
                tr.parse_traveler(bad, {10})

    def test_where(self):
        self.assertEqual(tr.where_is(self.MOVES), {"where": tr.IN_BAG, "user_id": 3})
        self.assertEqual(tr.where_is(self.MOVES[:3]), {"where": tr.AT_TREASURE, "treasure_id": 20})
        self.assertEqual(tr.last_place(self.MOVES), 20)
        self.assertEqual(tr.stops(self.MOVES), [10, 20])

    def test_pick(self):
        at20 = self.MOVES[:3]
        self.assertIsNone(tr.pick_problem(at20, 4, 20, 0))
        self.assertEqual(tr.pick_problem(at20, 4, None, 0), tr.NOT_NEAR)
        self.assertEqual(tr.pick_problem(at20, 4, 10, 0), tr.NOT_HERE)
        self.assertEqual(tr.pick_problem(at20, 4, 20, 1), tr.FULL_BAG)
        self.assertEqual(tr.pick_problem(self.MOVES, 4, 20, 0), tr.TAKEN)

    def test_drop(self):
        self.assertIsNone(tr.drop_problem(self.MOVES, 3, 30))
        self.assertEqual(tr.drop_problem(self.MOVES, 4, 30), tr.NOT_YOURS)
        self.assertEqual(tr.drop_problem(self.MOVES, 3, 20), tr.SAME_PLACE)
        self.assertEqual(tr.drop_problem(self.MOVES, 3, None), tr.NOT_NEAR)

    def test_release_goal_and_journey(self):
        self.assertIsNone(tr.release_problem(10, 2))
        self.assertEqual(tr.release_problem(10, 3), tr.TOO_MANY)
        self.assertEqual(tr.release_problem(None, 0), tr.NOT_NEAR)
        self.assertEqual(tr.reached_goal(self.MOVES, 20), 2)
        self.assertIsNone(tr.reached_goal(self.MOVES, 10))   # released there, never dropped there
        self.assertIsNone(tr.reached_goal(self.MOVES, None))
        self.assertEqual(tr.journey_m([(24.7950, 120.995), (24.7959, 120.995)]), 100)
        self.assertEqual(tr.distance_text(1530), "1.5 km")

    def test_nearest_treasure(self):
        places = [(1, 24.7950, 120.9950), (2, 24.79505, 120.9950), (3, 24.80, 121.0)]
        self.assertEqual(tr.nearest_treasure(24.79506, 120.9950, places)[0], 2)
        self.assertIsNone(tr.nearest_treasure(24.70, 120.9, places))


class GuideTest(unittest.TestCase):
    def test_bearing_and_compass(self):
        self.assertAlmostEqual(guide.bearing_deg(24.79, 120.99, 24.80, 120.99), 0, places=3)
        self.assertAlmostEqual(guide.bearing_deg(24.79, 120.99, 24.79, 121.00), 90, delta=0.1)
        self.assertEqual(guide.compass_word(44), "north-east")
        self.assertEqual(guide.compass_word(350), "north")

    def test_turn(self):
        self.assertEqual(guide.turn(90, 85), guide.AHEAD)
        self.assertEqual(guide.turn(90, 50), guide.SLIGHT_RIGHT)
        self.assertEqual(guide.turn(90, 0), guide.RIGHT)
        self.assertEqual(guide.turn(0, 90), guide.LEFT)
        self.assertEqual(guide.turn(10, 340), guide.SLIGHT_RIGHT)  # across north
        self.assertEqual(guide.turn(0, 180), guide.BEHIND)

    def test_beeps_get_faster(self):
        gaps = [guide.beep_gap_ms(d) for d in (500, 300, 150, 50, 10)]
        self.assertEqual(gaps, sorted(gaps, reverse=True))
        self.assertEqual(gaps[0], guide.SLOW_GAP_MS)
        self.assertEqual(gaps[-1], guide.FAST_GAP_MS)

    def test_guide(self):
        found = guide.guide("Pond", FOUND_RADIUS_M - 1, 0, 0)
        self.assertTrue(found["found"])
        no_compass = guide.guide("Pond", 123, 90)
        self.assertEqual(no_compass["words"], "Pond: 120 metres to the east.")
        turning = guide.guide("Pond", 40, 90, 0)
        self.assertEqual(turning["words"], "Pond: 40 metres, to your right.")
        self.assertEqual(turning["buzz"], guide.BUZZ[guide.RIGHT])
        self.assertIn("straight ahead", guide.guide("Pond", 2500, 90, 90)["words"])
        self.assertIn("2.5 kilometres", guide.guide("Pond", 2500, 90, 90)["words"])


if __name__ == "__main__":
    unittest.main()

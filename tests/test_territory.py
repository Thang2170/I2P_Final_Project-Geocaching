"""Claim the campus: hexagons, teams, visits and the weekly scoreboard (territory.py, territory_api.py)."""

import unittest
from datetime import datetime, timedelta, timezone

from app import create_app
from location import haversine_m
from models import HexVisit, User, db
from territory import (HEX_SIZE_M, ORIGIN, TEAMS, hex_centre, hex_corners, hex_of, leader, owners,
                       parse_team, scoreboard)
from walk_proof_api import record_point


class TestHexagons(unittest.TestCase):
    def test_origin_is_hexagon_zero(self):
        self.assertEqual(hex_of(*ORIGIN), (0, 0))

    def test_centre_round_trip(self):
        for cell in [(0, 0), (3, -2), (-5, 7), (12, 4)]:
            with self.subTest(cell):
                self.assertEqual(hex_of(*hex_centre(*cell)), cell)

    def test_shape(self):
        corners = hex_corners(2, -1)
        self.assertEqual(len(corners), 6)
        centre = hex_centre(2, -1)
        for corner in corners:
            self.assertAlmostEqual(haversine_m(*centre, *corner), HEX_SIZE_M, delta=0.5)
        # neighbours are sqrt(3) x size apart: about 69 m
        self.assertAlmostEqual(haversine_m(*hex_centre(0, 0), *hex_centre(1, 0)), HEX_SIZE_M * 3 ** 0.5, delta=0.5)

    def test_nearby_points_share_a_hexagon(self):
        lat, lon = hex_centre(4, 4)
        self.assertEqual(hex_of(lat + 0.0001, lon), (4, 4))  # 11 m away: same tile


class TestOwnership(unittest.TestCase):
    def test_most_visits_wins_and_ties_are_contested(self):
        visits = [(0, 0, "gold"), (0, 0, "gold"), (0, 0, "teal"), (1, 0, "teal"), (1, 0, "coral")]
        self.assertEqual(owners(visits), {(0, 0): "gold", (1, 0): None})

    def test_scoreboard_and_leader(self):
        board = scoreboard({(0, 0): "teal", (1, 0): "teal", (2, 0): "gold", (3, 0): None}, {"teal": 2})
        self.assertEqual([(t["id"], t["hexes"], t["players"]) for t in board],
                         [("teal", 2, 2), ("gold", 1, 0), ("coral", 0, 0)])
        self.assertEqual(leader(board), "teal")
        self.assertIsNone(leader(scoreboard({(0, 0): "teal", (1, 0): "gold"}, {})))  # level
        self.assertIsNone(leader(scoreboard({}, {})))                                 # nothing yet

    def test_team_choice(self):
        self.assertEqual(parse_team({"team": "coral"}), "coral")
        for bad in ({"team": "purple"}, {}, None):
            with self.subTest(bad), self.assertRaises(ValueError):
                parse_team(bad)


class TestApi(unittest.TestCase):
    def setUp(self):
        self.app = create_app("sqlite:///:memory:")
        self.context = self.app.app_context()
        self.context.push()
        self.ann, self.ann_id = self.player("ann")
        self.bob, self.bob_id = self.player("bob")

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
        self.context.pop()

    def player(self, name):
        client = self.app.test_client()
        client.post("/api/register", json={"username": name, "password": "secret1"})
        return client, db.session.execute(db.select(User.id).filter_by(username=name)).scalar_one()

    def walk(self, client, *cells):
        for cell in cells:
            lat, lon = hex_centre(*cell)
            client.post("/api/me/position", json={"lat": lat, "lon": lon})

    def board(self, client):
        return client.get("/api/territory").get_json()

    def test_needs_login(self):
        guest = self.app.test_client()
        self.assertEqual(guest.get("/api/territory").status_code, 401)
        self.assertEqual(guest.post("/api/territory/team", json={"team": "gold"}).status_code, 401)

    def test_no_team_no_visits(self):
        self.walk(self.ann, (0, 0))
        self.assertEqual(db.session.query(HexVisit).count(), 0)
        self.assertIsNone(self.board(self.ann)["my_team"])

    def test_walking_claims_hexagons(self):
        self.assertEqual(self.ann.post("/api/territory/team", json={"team": "teal"}).get_json()["name"], "Teal")
        self.walk(self.ann, (0, 0), (1, 0), (0, 0))  # (0, 0) twice today: one visit
        data = self.board(self.ann)
        self.assertEqual((data["my_team"], data["my_visits"]), ("teal", 2))
        self.assertEqual(sorted((h["q"], h["r"], h["team"]) for h in data["hexes"]), [(0, 0, "teal"), (1, 0, "teal")])
        self.assertEqual(data["leader"], "teal")
        self.assertEqual(len(data["hexes"][0]["corners"]), 6)

    def test_rivals_and_ties(self):
        self.ann.post("/api/territory/team", json={"team": "teal"})
        self.bob.post("/api/territory/team", json={"team": "gold"})
        self.walk(self.ann, (0, 0))
        self.walk(self.bob, (0, 0), (1, 0))
        hexes = {(h["q"], h["r"]): h for h in self.board(self.ann)["hexes"]}
        self.assertIsNone(hexes[(0, 0)]["team"])   # one visit each: contested
        self.assertEqual(hexes[(1, 0)]["team"], "gold")
        self.assertEqual(self.board(self.bob)["leader"], "gold")

    def test_teleports_dont_claim(self):
        self.ann.post("/api/territory/team", json={"team": "coral"})
        now = datetime.now(timezone.utc)
        far, here = hex_centre(40, 0), hex_centre(0, 0)  # about 2.8 km apart
        record_point(self.ann_id, *far, when=now - timedelta(seconds=5))
        record_point(self.ann_id, *here, when=now)  # 2.8 km in 5 seconds
        db.session.commit()
        cells = {(v.q, v.r) for v in db.session.query(HexVisit).all()}
        self.assertIn(hex_of(*far), cells)
        self.assertNotIn((0, 0), cells)

    def test_switching_team_keeps_old_visits(self):
        self.ann.post("/api/territory/team", json={"team": "teal"})
        self.walk(self.ann, (0, 0))
        self.ann.post("/api/territory/team", json={"team": "gold"})
        self.walk(self.ann, (1, 0))
        teams = {(v.q, v.r): v.team for v in db.session.query(HexVisit).all()}
        self.assertEqual(teams, {(0, 0): "teal", (1, 0): "gold"})

    def test_bad_team(self):
        self.assertEqual(self.ann.post("/api/territory/team", json={"team": "pink"}).status_code, 400)

    def test_page(self):
        html = self.ann.get("/territory").get_data(as_text=True)
        self.assertIn('fetch("/api/territory")', html)
        self.assertEqual(html.count('class="btn btn--ghost team-pick"'), len(TEAMS))
        self.assertIn('href="/territory"', html)  # the top bar link
        self.assertNotIn(".innerHTML", html)


if __name__ == "__main__":
    unittest.main()

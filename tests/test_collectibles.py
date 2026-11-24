import io
import json
import os
import shutil
import struct
import tempfile
from datetime import datetime, timedelta, timezone
import unittest
from unittest.mock import patch

from app import create_app
from collectibles import (CODE_LENGTH, MAX_MODEL_BYTES, can_manage, check_glb, clean_code, make_code,
                          parse_name, parse_trophy, still_to_find, utc_iso)
from models import db
from pixel_art import SPRITES
from voxel_models import (DEPTH, OUTPUT_DIR, PIXEL_CSS, TROPHIES, build_mesh, glb_bytes, letter_colours,
                          srgb_to_linear, trophy_glb)


def tiny_glb():
    """The smallest valid .glb: a header and a JSON chunk."""
    body = json.dumps({"asset": {"version": "2.0"}}).encode()
    body += b" " * ((4 - len(body) % 4) % 4)
    total = 12 + 8 + len(body)
    return struct.pack("<4sII", b"glTF", 2, total) + struct.pack("<I4s", len(body), b"JSON") + body


class TestRules(unittest.TestCase):
    def test_codes_are_random_and_readable(self):
        codes = {make_code() for _ in range(50)}
        self.assertEqual(len(codes), 50)
        for code in codes:
            self.assertEqual(clean_code(code), code)

    def test_clean_code_accepts_links_and_messy_typing(self):
        code = make_code()
        self.assertEqual(clean_code(f"https://stepquest.example/collect/{code}/"), code)
        self.assertEqual(clean_code(f"  {code[:5].lower()}-{code[5:]} "), code)

    def test_bad_codes(self):
        for bad in [None, "", "abc", "O" * CODE_LENGTH, "1" * CODE_LENGTH, "https://x/collect/"]:
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    clean_code(bad)

    def test_trophy_and_name(self):
        self.assertEqual(parse_trophy(""), "trophy")
        self.assertEqual(parse_trophy("coffee"), "coffee")
        with self.assertRaises(ValueError):
            parse_trophy("dragon")
        self.assertEqual(parse_name("", "Pond trophy"), "Pond trophy")
        with self.assertRaises(ValueError):
            parse_name("x" * 41, "d")

    def test_who_can_manage(self):
        self.assertTrue(can_manage(5, 5, False))
        self.assertFalse(can_manage(6, 5, False))
        self.assertTrue(can_manage(6, 5, True))
        self.assertFalse(can_manage(6, None, False))  # demo treasures: admins only

    def test_check_glb(self):
        self.assertTrue(check_glb(tiny_glb()))
        self.assertTrue(check_glb(trophy_glb("trophy")))
        bad_files = {
            "empty": b"",
            "picture": b"\x89PNG\r\n\x1a\n" + b"0" * 40,
            "version 1": tiny_glb().replace(struct.pack("<I", 2), struct.pack("<I", 1), 1),
            "cut short": tiny_glb()[:-4],
            "too big": b"glTF" + b"0" * MAX_MODEL_BYTES,
        }
        for name, data in bad_files.items():
            with self.subTest(file=name):
                with self.assertRaises(ValueError):
                    check_glb(data)


    def test_utc_iso_keeps_the_time_zone(self):
        naive = datetime(2026, 11, 24, 6, 5)  # what SQLite gives back
        self.assertEqual(utc_iso(naive), "2026-11-24T06:05:00+00:00")
        taipei = datetime(2026, 11, 24, 14, 5, tzinfo=timezone(timedelta(hours=8)))
        self.assertEqual(utc_iso(taipei), "2026-11-24T14:05:00+08:00")
        self.assertIsNone(utc_iso(None))

    def test_still_to_find(self):
        self.assertEqual(still_to_find(10, 2, 3), 5)
        self.assertEqual(still_to_find(3, 0, 3), 0)
        self.assertEqual(still_to_find(1, 1, 1), 0)  # never below zero


class TestVoxelModels(unittest.TestCase):
    def test_srgb_to_linear(self):
        self.assertEqual(srgb_to_linear(0), 0)
        self.assertAlmostEqual(srgb_to_linear(255), 1)
        self.assertAlmostEqual(srgb_to_linear(128), 0.2158, places=3)

    def test_one_pixel_is_one_cube(self):
        positions, normals, indices = build_mesh(["o"], depth=1)["o"]
        self.assertEqual(len(positions), 24)  # 6 faces x 4 corners
        self.assertEqual(len(indices), 36)    # 6 faces x 2 triangles x 3 corners

    def test_hidden_faces_between_blocks_are_skipped(self):
        two = build_mesh(["oo"], depth=1)["o"][0]
        self.assertEqual(len(two), 2 * 24 - 2 * 4)  # the face where they touch is gone on both

    def test_blocks_are_grouped_by_colour(self):
        groups = build_mesh(["oy", "y."], depth=1)
        self.assertEqual(sorted(groups), ["o", "y"])
        self.assertEqual(len(groups["o"][0]), 24 - 2 * 4)  # touches y on its right and below

    def read_gltf(self, data):
        return json.loads(data[20:20 + struct.unpack_from("<I", data, 12)[0]])

    def test_glb_header_and_size(self):
        data = trophy_glb("trophy")
        magic, version, length = struct.unpack_from("<4sII", data)
        self.assertEqual((magic, version, length), (b"glTF", 2, len(data)))
        self.assertEqual(len(data) % 4, 0)
        info = self.read_gltf(data)
        bottoms = [a["min"][1] for a in info["accessors"] if "min" in a]
        tops = [a["max"][1] for a in info["accessors"] if "max" in a]
        self.assertAlmostEqual(min(bottoms), 0)  # stands on the floor
        self.assertGreater(max(tops), 0.2)       # about 26 cm tall in AR

    def test_colours_are_materials_so_ar_shows_them(self):
        # Phone AR ignores colours stored on corners (COLOR_0): that made the trophy white.
        colours = letter_colours(PIXEL_CSS.read_text(encoding="utf-8"))
        info = self.read_gltf(trophy_glb("trophy"))
        for primitive in info["meshes"][0]["primitives"]:
            self.assertNotIn("COLOR_0", primitive["attributes"])
        used = {tuple(m["pbrMetallicRoughness"]["baseColorFactor"]) for m in info["materials"]}
        letters = {ch for row in SPRITES["trophy"][0] for ch in row if ch != "."}
        self.assertEqual(used, {colours[ch] for ch in letters})
        self.assertNotIn((1, 1, 1, 1), used)  # not one plain white material any more

    def test_saved_trophies_match_the_pixel_art(self):
        # If this fails: run  python voxel_models.py
        for name in TROPHIES:
            with self.subTest(trophy=name):
                self.assertEqual((OUTPUT_DIR / f"{name}.glb").read_bytes(), trophy_glb(name))

    def test_depth(self):
        self.assertGreaterEqual(DEPTH, 1)
        one = {"o": ([(0, 0, 0)] * 3, [(0, 0, 1)] * 3, [0, 1, 2])}
        self.assertIsInstance(glb_bytes(one, {"o": (1, 0, 0, 1)}), bytes)
        self.assertTrue(check_glb(glb_bytes(one, {"o": (1, 0, 0, 1)})))


class TestCollectibleApi(unittest.TestCase):
    def setUp(self):
        self.instance = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.instance, True)
        self.env = patch.dict(os.environ, {"ADMIN_USERS": "admin"})
        self.env.start()
        self.app = create_app("sqlite:///:memory:")
        self.app.instance_path = self.instance  # uploaded models go to a throwaway folder
        self.context = self.app.app_context()
        self.context.push()
        self.alice, self.bao = self.player("alice"), self.player("bao")
        self.tid = self.alice.post("/api/treasures", json={"name": "Pond", "lat": 24.80, "lon": 120.99}).get_json()["id"]

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
        self.context.pop()
        self.env.stop()

    def player(self, name):
        client = self.app.test_client()
        client.post("/api/register", json={"username": name, "password": "secret1"})
        return client

    def set_up(self, client, **form):
        return client.post(f"/api/treasures/{self.tid}/collectible", data=form,
                           content_type="multipart/form-data")

    def test_hider_sets_up_and_another_player_collects(self):
        r = self.set_up(self.alice, name="Pond cup", trophy="trophy")
        self.assertEqual(r.status_code, 201)
        code = r.get_json()["code"]
        listed = {t["name"]: t for t in self.bao.get("/api/treasures").get_json()}
        self.assertTrue(listed["Pond"]["collectible"])
        self.assertFalse(listed["Pond"]["collected_by_me"])

        first = self.bao.post("/api/collect", json={"code": code}).get_json()
        self.assertTrue(first["new"])
        self.assertEqual(first["item"]["name"], "Pond cup")
        self.assertFalse(self.bao.post("/api/collect", json={"code": code}).get_json()["new"])  # only once
        shelf = self.bao.get("/api/collection").get_json()
        mine = shelf["mine"]
        self.assertEqual([m["name"] for m in mine], ["Pond cup"])
        # where and when, for the shelf card
        self.assertEqual((mine[0]["treasure"], mine[0]["lat"], mine[0]["lon"]), ("Pond", 24.80, 120.99))
        self.assertTrue(mine[0]["collected_at"].endswith("+00:00"))
        self.assertEqual(shelf["to_find"], 0)
        self.assertTrue({t["name"]: t for t in self.bao.get("/api/treasures").get_json()}["Pond"]["collected_by_me"])

    def test_empty_shelf_spots(self):
        self.set_up(self.alice)
        self.assertEqual(self.bao.get("/api/collection").get_json()["to_find"], 1)
        self.assertEqual(self.alice.get("/api/collection").get_json()["to_find"], 0)  # her own

    def here(self, client, lat=24.80, lon=120.99, tid=None):
        return client.post(f"/api/treasures/{tid or self.tid}/collect-here", json={"lat": lat, "lon": lon})

    def test_collect_by_walking_there(self):
        self.set_up(self.alice, name="Pond cup")
        first = self.here(self.bao, lat=24.80005)  # about 6 m away: close enough
        self.assertEqual(first.status_code, 200)
        self.assertEqual((first.get_json()["new"], first.get_json()["item"]["name"]), (True, "Pond cup"))
        self.assertFalse(self.here(self.bao).get_json()["new"])  # only once
        self.assertEqual(len(self.bao.get("/api/collection").get_json()["mine"]), 1)

    def test_collect_here_too_far(self):
        self.set_up(self.alice)
        r = self.here(self.bao, lat=24.801)  # about 111 m away
        self.assertEqual(r.status_code, 400)
        self.assertIn("m away", r.get_json()["error"])
        self.assertEqual(self.bao.get("/api/collection").get_json()["mine"], [])

    def test_collect_here_refusals(self):
        self.assertEqual(self.here(self.bao).status_code, 404)              # no collectible yet
        self.set_up(self.alice)
        self.assertEqual(self.here(self.bao, tid=9999).status_code, 404)    # no such treasure
        self.assertEqual(self.here(self.alice).status_code, 403)            # you hid it yourself
        self.assertEqual(self.here(self.app.test_client()).status_code, 401)
        bad = self.bao.post(f"/api/treasures/{self.tid}/collect-here", json={"lat": "north"})
        self.assertEqual(bad.status_code, 400)
        self.assertEqual(self.bao.post(f"/api/treasures/{self.tid}/collect-here", data="x").status_code, 400)

    def test_scanning_the_printed_link(self):
        code = self.set_up(self.alice).get_json()["code"]
        r = self.bao.get(f"/collect/{code}")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/collection?new=", r.headers["Location"])
        self.assertIn("/login", self.app.test_client().get(f"/collect/{code}").headers["Location"])

    def test_cannot_collect_your_own(self):
        code = self.set_up(self.alice).get_json()["code"]
        r = self.alice.post("/api/collect", json={"code": code})
        self.assertEqual(r.status_code, 400)
        self.assertIn("yourself", r.get_json()["error"])

    def test_wrong_code(self):
        self.assertEqual(self.bao.post("/api/collect", json={"code": make_code()}).status_code, 400)
        self.assertEqual(self.bao.post("/api/collect", json={"code": "nope"}).status_code, 400)

    def test_only_the_hider_or_an_admin_can_set_up(self):
        self.assertEqual(self.set_up(self.bao).status_code, 403)
        self.assertEqual(self.set_up(self.player("admin")).status_code, 201)

    def test_changing_keeps_the_qr_code(self):
        code = self.set_up(self.alice, trophy="coffee").get_json()["code"]
        again = self.set_up(self.alice, trophy="badge").get_json()
        self.assertEqual((again["code"], again["trophy"]), (code, "badge"))

    def test_handmade_model_upload(self):
        r = self.set_up(self.alice, name="My clay cat", model=(io.BytesIO(tiny_glb()), "cat.glb"))
        data = r.get_json()
        self.assertEqual((r.status_code, data["uploaded"]), (201, True))
        model = self.bao.get(data["model_url"])
        self.assertEqual(model.status_code, 200)
        self.assertEqual(model.data, tiny_glb())
        model.close()

    def test_fake_model_is_refused(self):
        r = self.set_up(self.alice, model=(io.BytesIO(b"MZ this is really a program"), "trophy.glb"))
        self.assertEqual(r.status_code, 400)

    def test_built_in_model_link(self):
        cid = self.set_up(self.alice, trophy="coffee").get_json()["id"]
        r = self.bao.get(f"/api/collectibles/{cid}/model.glb")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/static/models/coffee.glb", r.headers["Location"])

    def test_qr_page_is_for_the_hider(self):
        self.set_up(self.alice)
        page = self.alice.get(f"/treasures/{self.tid}/qr")
        self.assertEqual(page.status_code, 200)
        self.assertIn("<svg", page.get_data(as_text=True))  # Python drew the QR code
        self.assertEqual(self.bao.get(f"/treasures/{self.tid}/qr").status_code, 403)

    def test_pages_and_login(self):
        self.assertEqual(self.bao.get("/collection").status_code, 200)
        self.assertEqual(self.bao.get("/scan").status_code, 200)
        self.assertIn("/login", self.app.test_client().get("/collection").headers["Location"])
        self.assertEqual(self.app.test_client().get("/api/collection").status_code, 401)


if __name__ == "__main__":
    unittest.main()

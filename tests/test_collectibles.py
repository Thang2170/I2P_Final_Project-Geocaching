import io
import json
import os
import shutil
import struct
import tempfile
import unittest
from unittest.mock import patch

from app import create_app
from collectibles import (CODE_LENGTH, MAX_MODEL_BYTES, can_manage, check_glb, clean_code, make_code,
                          parse_name, parse_trophy)
from models import db
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


class TestVoxelModels(unittest.TestCase):
    def test_srgb_to_linear(self):
        self.assertEqual(srgb_to_linear(0), 0)
        self.assertAlmostEqual(srgb_to_linear(255), 1)
        self.assertAlmostEqual(srgb_to_linear(128), 0.2158, places=3)

    def test_one_pixel_is_one_cube(self):
        colours = letter_colours(PIXEL_CSS.read_text(encoding="utf-8"))
        positions, normals, cols, indices = build_mesh(["o"], colours, depth=1)
        self.assertEqual(len(positions), 24)  # 6 faces x 4 corners
        self.assertEqual(len(indices), 36)    # 6 faces x 2 triangles x 3 corners

    def test_hidden_faces_between_blocks_are_skipped(self):
        colours = letter_colours(PIXEL_CSS.read_text(encoding="utf-8"))
        two = build_mesh(["oo"], colours, depth=1)[0]
        self.assertEqual(len(two), 2 * 24 - 2 * 4)  # the face where they touch is gone on both

    def test_glb_header_and_size(self):
        data = trophy_glb("trophy")
        magic, version, length = struct.unpack_from("<4sII", data)
        self.assertEqual((magic, version, length), (b"glTF", 2, len(data)))
        self.assertEqual(len(data) % 4, 0)
        info = json.loads(data[20:20 + struct.unpack_from("<I", data, 12)[0]])
        self.assertEqual(info["meshes"][0]["primitives"][0]["attributes"]["COLOR_0"], 2)
        top = info["accessors"][0]["max"][1]
        self.assertAlmostEqual(info["accessors"][0]["min"][1], 0)  # stands on the floor
        self.assertGreater(top, 0.2)  # about 26 cm tall in AR

    def test_saved_trophies_match_the_pixel_art(self):
        # If this fails: run  python voxel_models.py
        for name in TROPHIES:
            with self.subTest(trophy=name):
                self.assertEqual((OUTPUT_DIR / f"{name}.glb").read_bytes(), trophy_glb(name))

    def test_depth(self):
        self.assertGreaterEqual(DEPTH, 1)
        self.assertIsInstance(glb_bytes([(0, 0, 0)] * 3, [(0, 0, 1)] * 3, [(1, 1, 1, 1)] * 3, [0, 1, 2]), bytes)


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
        mine = self.bao.get("/api/collection").get_json()["mine"]
        self.assertEqual([m["name"] for m in mine], ["Pond cup"])
        self.assertTrue({t["name"]: t for t in self.bao.get("/api/treasures").get_json()}["Pond"]["collected_by_me"])

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

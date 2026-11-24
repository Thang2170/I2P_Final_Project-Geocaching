"""Install as an app: icons, manifest, service worker, offline page (app_icon.py, pwa_api.py, sw.js)."""

import struct
import unittest
import zlib
from pathlib import Path

from app import create_app
from app_icon import BACKGROUND, SIZES, icon_files, icon_pixels, png_bytes, rgb
from models import db
from pixel_art import COIN_FULL
from pwa_api import manifest
from tests import PROJECT_ROOT

STATIC = Path(PROJECT_ROOT) / "static"


class TestIcon(unittest.TestCase):
    def test_png_is_valid(self):
        data = png_bytes([[(255, 0, 0), (0, 255, 0)], [(0, 0, 255), (0, 0, 0)]])
        self.assertTrue(data.startswith(b"\x89PNG\r\n\x1a\n"))
        width, height = struct.unpack(">II", data[16:24])
        self.assertEqual((width, height), (2, 2))
        idat = data.index(b"IDAT")
        length = struct.unpack(">I", data[idat - 4:idat])[0]
        raw = zlib.decompress(data[idat + 4:idat + 4 + length])
        self.assertEqual(raw, b"\x00\xff\x00\x00\x00\xff\x00\x00\x00\x00\xff\x00\x00\x00")

    def test_coin_is_centred_on_the_background(self):
        grid = icon_pixels(COIN_FULL, 192)
        self.assertEqual(len(grid), 192)
        self.assertEqual(grid[0][0], rgb(BACKGROUND))          # a corner: background
        self.assertNotEqual(grid[96][96], rgb(BACKGROUND))     # the middle: the coin

    def test_saved_icons_match_the_pixel_art(self):
        """Fails if pixel_art.py's coin changed without running `python app_icon.py`."""
        for name, data in icon_files().items():
            with self.subTest(name):
                self.assertEqual((STATIC / "icons" / name).read_bytes(), data)


class TestManifestAndPages(unittest.TestCase):
    def setUp(self):
        self.app = create_app("sqlite:///:memory:")
        self.client = self.app.test_client()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()
            db.engine.dispose()

    def test_manifest(self):
        m = manifest()
        self.assertEqual((m["short_name"], m["start_url"], m["display"]), ("StepQuest", "/", "standalone"))
        self.assertEqual([i["sizes"] for i in m["icons"]], [f"{s}x{s}" for s in SIZES])
        r = self.client.get("/manifest.webmanifest")
        self.assertEqual(r.mimetype, "application/manifest+json")
        for icon in r.get_json()["icons"]:
            with self.subTest(icon["src"]):
                self.assertTrue((Path(PROJECT_ROOT) / icon["src"].lstrip("/")).is_file())

    def test_service_worker_is_served_from_the_root(self):
        r = self.client.get("/sw.js")
        self.assertEqual((r.status_code, r.mimetype), (200, "text/javascript"))
        self.assertEqual(r.headers["Service-Worker-Allowed"], "/")
        body = r.get_data(as_text=True)
        r.close()
        self.assertIn('url.pathname.startsWith("/api/")', body)  # live game data is never cached
        for path in ("/offline", "/static/css/app.css"):
            self.assertIn(f'"{path}"', body)

    def test_every_cached_file_exists(self):
        body = (STATIC / "js" / "sw.js").read_text(encoding="utf-8")
        shell = body.split("const SHELL = [", 1)[1].split("];", 1)[0]
        for line in shell.split(","):
            path = line.strip().strip('"')
            if path.startswith("/static/"):
                with self.subTest(path):
                    self.assertTrue((Path(PROJECT_ROOT) / path.lstrip("/")).is_file())

    def test_offline_page(self):
        r = self.client.get("/offline")
        self.assertEqual(r.status_code, 200)
        self.assertIn("You're offline", r.get_data(as_text=True))

    def test_every_page_links_the_manifest(self):
        html = self.client.get("/login").get_data(as_text=True)
        self.assertIn('rel="manifest" href="/manifest.webmanifest"', html)
        self.assertIn("js/install.js", html)
        self.assertIn("data-install hidden", html)


if __name__ == "__main__":
    unittest.main()

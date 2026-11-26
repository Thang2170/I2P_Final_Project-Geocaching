"""A: random pixel landscapes (scenery.py) and the creatures that became trophies."""

import random
import unittest

from app import create_app
from pixel_art import SPRITES
from scenery import FLYERS, GROUND_TOP_PX, SCENES, pick_scene, sky_css
from voxel_models import TROPHIES

HAND_DRAWN = {"tree"}  # drawn in pixel.css, not in pixel_art.py


class TestPickScene(unittest.TestCase):
    def test_every_landscape_can_come_up_and_is_complete(self):
        seen = set()
        for seed in range(60):
            scene = pick_scene(random.Random(seed))
            seen.add(scene["name"])
            kinds = {item["kind"] for item in scene["items"]}
            with self.subTest(seed=seed):
                self.assertTrue({"prop", "fall"} <= kinds)
                self.assertTrue(kinds & {"walker", "flyer"})        # at least one creature
                self.assertTrue(scene["sky"].startswith("linear-gradient"))
        self.assertEqual(seen, set(SCENES))

    def test_items_stay_on_screen_and_in_their_place(self):
        for seed in range(40):
            for item in pick_scene(random.Random(seed))["items"]:
                with self.subTest(seed=seed, item=item["sprite"]):
                    self.assertTrue(0 <= item["left"] <= 100)
                    if item["kind"] == "flyer":
                        self.assertIn(item["sprite"], FLYERS)
                        self.assertGreater(item["bottom"], GROUND_TOP_PX)   # in the sky
                        self.assertGreaterEqual(item["left"], 55)           # away from the headline
                    if item["kind"] == "walker":
                        self.assertNotIn(item["sprite"], FLYERS)
                        self.assertLess(item["bottom"], GROUND_TOP_PX)      # on the grass

    def test_every_picture_exists(self):
        for name, scene in SCENES.items():
            names = scene["props"] + scene["creatures"] + [scene["falling"]] + [scene["landmark"] or "rock"]
            for sprite in names:
                with self.subTest(scene=name, sprite=sprite):
                    self.assertTrue(sprite in SPRITES or sprite in HAND_DRAWN)

    def test_same_seed_same_scene(self):
        self.assertEqual(pick_scene(random.Random(7)), pick_scene(random.Random(7)))

    def test_sky_bands(self):
        self.assertEqual(sky_css(("#1", "#2", "#3", "#4")),
                         "linear-gradient(to bottom, #1 0 36%, #2 36% 52%, #3 52% 64%, #4 64% 100%)")


class TestPages(unittest.TestCase):
    def test_login_and_welcome_draw_a_landscape(self):
        app = create_app("sqlite:///:memory:")
        client = app.test_client()
        for page in ("/login", "/welcome"):
            html = client.get(page).get_data(as_text=True)
            with self.subTest(page=page):
                self.assertIn('class="scene scene--', html)
                self.assertIn("--scene-sky: linear-gradient", html)
                self.assertIn("scene-item--fall", html)


class TestCreatureTrophies(unittest.TestCase):
    def test_creatures_can_be_collected(self):
        for name in ("cat", "dog", "butterfly", "bird", "sakura", "pine"):
            self.assertIn(name, TROPHIES)
            self.assertIn(name, SPRITES)


if __name__ == "__main__":
    unittest.main()

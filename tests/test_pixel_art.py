import unittest

import pixel_art
from pixel_art import OUTPUT, PALETTE, SPRITES, box_shadow, build_css, check_sprite, sprite_css
from tests import PROJECT_ROOT


class TestPictures(unittest.TestCase):
    def test_every_picture_is_well_drawn(self):
        # Same-width rows, same-size frames, only colours from PALETTE
        for name, frames in SPRITES.items():
            with self.subTest(sprite=name):
                width, height = check_sprite(name, frames)
                self.assertGreater(width, 0)
                self.assertGreater(height, 0)

    def test_every_colour_is_a_palette_variable(self):
        for letter, variable in PALETTE.items():
            with self.subTest(letter=letter):
                self.assertTrue(variable.startswith("--px-"))

    def test_broken_pictures_are_caught(self):
        with self.assertRaises(ValueError):
            check_sprite("uneven", [["oo", "ooo"]])
        with self.assertRaises(ValueError):
            check_sprite("unknown colour", [["oZ"]])
        with self.assertRaises(ValueError):
            check_sprite("frames differ", [["oo"], ["oo", "oo"]])
        with self.assertRaises(ValueError):
            check_sprite("no frames", [])


class TestCss(unittest.TestCase):
    def test_one_shadow_per_coloured_pixel(self):
        css = box_shadow(["o.", ".g"])
        self.assertEqual(css.count("0 0 var("), 2)
        self.assertIn(f"{pixel_art.PIXEL}px {pixel_art.PIXEL}px 0 0 var(--px-ink)", css)
        self.assertIn(f"{2 * pixel_art.PIXEL}px {2 * pixel_art.PIXEL}px 0 0 var(--px-gold)", css)

    def test_size_comes_from_the_picture(self):
        css = sprite_css("tiny", [["ooo", "ooo"]])
        self.assertIn(f"width: {3 * pixel_art.PIXEL}px; height: {2 * pixel_art.PIXEL}px", css)

    def test_frames_become_an_animation_that_respects_less_motion(self):
        css = sprite_css("explorer", SPRITES["explorer"])
        self.assertIn("@keyframes sprite-explorer", css)
        self.assertIn("prefers-reduced-motion: reduce", css)
        self.assertNotIn("@keyframes", sprite_css("flag", SPRITES["flag"]))

    def test_saved_css_matches_the_pictures(self):
        # If this fails, someone changed a picture but forgot:  python pixel_art.py
        self.assertEqual(OUTPUT.read_text(encoding="utf-8"), build_css())


class TestPagesUseTheSprites(unittest.TestCase):
    def read(self, name):
        with open(f"{PROJECT_ROOT}/templates/{name}", encoding="utf-8") as f:
            return f.read()

    def test_every_page_loads_sprites_css(self):
        self.assertIn("css/sprites.css", self.read("_head.html"))
        self.assertIn("css/sprites.css", self.read("index.html"))

    def test_admin_tiles_have_art(self):
        html = self.read("admin.html")
        for sprite in ("explorer", "signal", "chest-open", "map", "coin-spin", "flag"):
            self.assertIn(f"sprite--{sprite} tile__art", html)

    def test_shop_items_have_art(self):
        html = self.read("shop.html")
        for sprite in ("bubble-tea", "coffee", "badge", "gold-pin"):
            self.assertIn(f'"{sprite}"', html)


class TestIcons(unittest.TestCase):
    """A: the small interface icons that replace emoji."""

    def test_icons_are_small_and_sharp(self):
        self.assertIn("icon-flame", pixel_art.ICONS)
        for name in pixel_art.ICONS:
            with self.subTest(icon=name):
                width, height = check_sprite(name, SPRITES[name])
                self.assertLessEqual(max(width, height), 12)            # about 20 px on screen
                self.assertEqual(pixel_art.PIXEL_SIZE[name], pixel_art.SMALL_PIXEL)
                self.assertIn(f".sprite--{name}::before {{ left: -2px;", sprite_css(name, SPRITES[name]))

    def test_the_flame_flickers_but_not_for_less_motion(self):
        css = sprite_css("icon-flame", SPRITES["icon-flame"])
        self.assertIn("animation: sprite-icon-flame", css)
        self.assertIn("prefers-reduced-motion", css)

    def test_every_weather_icon_exists(self):
        from weather import WEATHER_ICONS
        for icon in WEATHER_ICONS.values():
            self.assertIn(f"icon-{icon}", SPRITES)


if __name__ == "__main__":
    unittest.main()

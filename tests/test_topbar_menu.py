"""B: the top bar keeps Map, Hunts and Community; every other page is in the Menu."""

import re
import unittest

from app import create_app

MENU_PAGES = ("/upload", "/riddles", "/territory", "/trails", "/health", "/report", "/collection", "/shop",
              "/login", "/leaderboard", "/heatmap")


class TopbarMenuTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app("sqlite:///:memory:")
        self.client = self.app.test_client()
        self.client.post("/api/register", json={"username": "ann", "password": "secret1"})

    def bar(self, path):
        html = self.client.get(path).get_data(as_text=True)
        return html.split('<header class="topbar">', 1)[1].split("</header>", 1)[0]

    def test_bar_and_menu(self):
        bar = self.bar("/")
        outside = bar.split('<div class="menu"', 1)[0]
        panel = bar.split('id="menuPanel"', 1)[1]
        self.assertEqual(re.findall(r'href="([^"]+)"', outside), ["/welcome", "/", "/hunts", "/community"])
        for href in MENU_PAGES:
            self.assertIn(f'href="{href}"', panel)
        self.assertIn('aria-controls="menuPanel"', bar)
        self.assertIn('aria-expanded="false"', bar)
        self.assertIn('id="menuPanel" hidden', bar)

    def test_the_button_names_the_page_you_are_on(self):
        self.assertIn('<span class="menu__label">Shop</span>', self.bar("/shop"))
        self.assertIn('menu__button is-active', self.bar("/shop"))
        self.assertIn('<span class="menu__label">My trails</span>', self.bar("/trails"))
        self.assertIn('<span class="menu__label">Weekly report</span>', self.bar("/report"))
        self.assertIn('<span class="menu__label">Menu</span>', self.bar("/"))  # Map is in the bar itself
        self.assertIn('href="/" class="is-active"', self.bar("/"))

    def test_phone_layout(self):
        css = self.client.get("/static/css/app.css").get_data(as_text=True)
        self.assertIn(".topbar__nav > a { display: none; }", css)
        self.assertIn(".menu__small-only { display: block; }", css)


if __name__ == "__main__":
    unittest.main()

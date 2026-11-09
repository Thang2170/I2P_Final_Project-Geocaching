"""The shop page uses the shared look, and every page links to it."""

import unittest

from app import create_app
from models import db


class TestShopPages(unittest.TestCase):
    def setUp(self):
        self.app = create_app("sqlite:///:memory:")
        self.client = self.app.test_client()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()
            db.engine.dispose()

    def html(self, path):
        r = self.client.get(path)
        self.assertEqual(r.status_code, 200, path)
        return r.get_data(as_text=True)

    def test_shop_page_uses_shared_style_and_is_highlighted(self):
        html = self.html("/shop")
        self.assertIn("css/app.css", html)
        self.assertIn('href="/shop" class="is-active"', html)

    def test_other_pages_link_to_the_shop(self):
        for path in ["/upload", "/login"]:
            with self.subTest(path=path):
                self.assertIn('href="/shop"', self.html(path))

    def test_shop_page_sends_logged_out_visitors_to_login(self):
        self.assertIn("/login?next=/shop", self.html("/shop"))

    def test_shop_routes_are_registered_in_the_real_app(self):
        self.assertEqual(self.client.get("/api/shop/items").status_code, 200)

    def test_shop_page_has_a_popup_for_not_enough_coins(self):
        html = self.html("/shop")
        self.assertIn('id="toast"', html)
        self.assertIn("res.status === 402", html)
        self.assertIn("Not enough coins!", html)


if __name__ == "__main__":
    unittest.main()

"""B: map.html's script lives in parts (templates/map/*.js), pulled in when the page is built."""

import os
import re
import unittest

from app import create_app

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARTS_DIR = os.path.join(ROOT, "templates", "map")


class MapPartsTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app("sqlite:///:memory:")
        client = self.app.test_client()
        client.post("/api/register", json={"username": "ann", "password": "secret1"})
        self.page = client.get("/").get_data(as_text=True)
        self.template = open(os.path.join(ROOT, "templates", "map.html"), encoding="utf-8").read()

    def included(self):
        return re.findall(r'\{% include "map/([\w.]+)" %\}', self.template)

    def test_every_part_is_included_once(self):
        files = sorted(f for f in os.listdir(PARTS_DIR) if f.endswith(".js"))
        self.assertEqual(sorted(self.included()), files)
        self.assertEqual(len(self.included()), len(set(self.included())))

    def test_no_jinja_tags_in_the_parts(self):
        for name in self.included():
            text = open(os.path.join(PARTS_DIR, name), encoding="utf-8").read()
            for tag in ("{{", "{%", "{#"):
                self.assertNotIn(tag, text, f"{name} has {tag}: Flask would run it")

    def test_the_page_is_still_one_script(self):
        script = self.page.split('<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>', 1)[1]
        script = script.split("<script>", 1)[1].split("</script>", 1)[0]  # the map's own <script> ... </script>
        for name in self.included():
            first_code = next(line.strip() for line in open(os.path.join(PARTS_DIR, name), encoding="utf-8")
                              if line.strip() and not line.strip().startswith("//"))
            self.assertIn(first_code, script, name)
        self.assertIn("const treasure = {", script)          # the value from Python, filled in
        self.assertNotIn("{% include", self.page)

    def test_order_starts_with_the_map(self):
        self.assertEqual(self.included()[0], "map_view.js")  # everything else uses `map`


if __name__ == "__main__":
    unittest.main()

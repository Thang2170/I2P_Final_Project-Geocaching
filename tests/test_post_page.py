"""A post on its own page: /posts/<id>, opened from a profile's Posts list."""

import unittest

from app import create_app
from models import db


class TestPostPage(unittest.TestCase):
    def setUp(self):
        self.app = create_app("sqlite:///:memory:")
        self.context = self.app.app_context()
        self.context.push()
        self.ann, self.bob = self.player("ann"), self.player("bob")
        self.post_id = self.ann.post("/api/posts", json={"text": "Found the lake treasure"}).get_json()["id"]

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
        self.context.pop()

    def player(self, name):
        client = self.app.test_client()
        client.post("/api/register", json={"username": name, "password": "secret1"})
        return client

    def test_profile_posts_have_ids(self):
        posts = self.bob.get("/api/players/ann").get_json()["recent_posts"]
        self.assertEqual(posts[0]["id"], self.post_id)

    def test_one_post_api(self):
        self.bob.post(f"/api/posts/{self.post_id}/comments", json={"text": "Where?"})
        data = self.bob.get(f"/api/posts/{self.post_id}").get_json()
        self.assertEqual((data["post"]["text"], data["post"]["comment_count"], data["me"]["username"]),
                         ("Found the lake treasure", 1, "bob"))
        self.assertEqual(self.bob.get("/api/posts/999").status_code, 404)
        self.assertEqual(self.app.test_client().get(f"/api/posts/{self.post_id}").status_code, 401)

    def test_who_liked(self):
        self.bob.post(f"/api/posts/{self.post_id}/like")
        self.ann.post(f"/api/posts/{self.post_id}/like")
        likes = self.bob.get(f"/api/posts/{self.post_id}/likes").get_json()["likes"]
        self.assertEqual([(l["username"], l["is_me"]) for l in likes], [("ann", False), ("bob", True)])  # newest first
        self.assertEqual(likes[0]["avatar"]["letter"], "A")
        self.assertEqual(self.bob.get("/api/posts/999/likes").status_code, 404)
        self.assertEqual(self.app.test_client().get(f"/api/posts/{self.post_id}/likes").status_code, 401)
        html = self.bob.get("/community").get_data(as_text=True)
        self.assertIn("/likes`", html)
        self.assertIn('el("button", "", "post__likes")', html)

    def test_page(self):
        html = self.bob.get(f"/posts/{self.post_id}").get_data(as_text=True)
        self.assertIn(f"const singlePost = {self.post_id};", html)
        self.assertIn("Back to the Community feed", html)
        self.assertIn("<title>Post · StepQuest</title>", html)
        feed = self.bob.get("/community").get_data(as_text=True)
        self.assertIn("const singlePost = null;", feed)

    def test_profile_links_to_the_post(self):
        html = self.bob.get("/players/ann").get_data(as_text=True)
        self.assertIn("`/posts/${encodeURIComponent(post.id)}`", html)


if __name__ == "__main__":
    unittest.main()

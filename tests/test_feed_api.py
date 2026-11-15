import unittest

from app import create_app
from feed_rules import FEED_PAGE_SIZE
from models import Post, PostComment, PostLike, Treasure, db

LAT, LON = 24.795324, 120.994796


class TestFeedApi(unittest.TestCase):
    def setUp(self):
        # A throwaway in-memory database, so tests never touch geohunt.db.
        self.app = create_app("sqlite:///:memory:")
        self.context = self.app.app_context()
        self.context.push()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
        self.context.pop()

    def player(self, name):
        client = self.app.test_client()
        client.post("/api/register", json={"username": name, "password": "secret1"})
        return client

    def post(self, client, text="Hello"):
        return client.post("/api/posts", json={"text": text})

    def feed(self, client, offset=""):
        return client.get(f"/api/feed?offset={offset}").get_json()

    def finish_hunt(self, client, name="Pond", lat=LAT):
        treasure = Treasure(name=name, lat=lat, lon=LON)
        db.session.add(treasure)
        db.session.commit()
        r = client.post("/api/journeys", json={"treasure_id": treasure.id, "distance_m": 750,
                                               "duration_s": 600, "lat": lat, "lon": LON})
        self.assertEqual(r.status_code, 201)

    # ---------------------------------------------------------------- logging in

    def test_everything_needs_a_login(self):
        guest = self.app.test_client()
        self.assertEqual(guest.get("/api/feed").status_code, 401)
        self.assertEqual(self.post(guest).status_code, 401)
        self.assertEqual(guest.post("/api/posts/1/like").status_code, 401)
        self.assertEqual(guest.post("/api/posts/1/comments", json={"text": "hi"}).status_code, 401)
        self.assertEqual(guest.delete("/api/posts/1").status_code, 401)
        self.assertEqual(guest.delete("/api/comments/1").status_code, 401)

    # ---------------------------------------------------------------- posting

    def test_an_empty_feed_says_who_you_are(self):
        data = self.feed(self.player("ann"))
        self.assertEqual(data["posts"], [])
        self.assertEqual(data["me"]["username"], "ann")
        self.assertEqual(data["me"]["avatar"]["letter"], "A")
        self.assertIsNone(data["next_offset"])

    def test_write_a_post(self):
        ann = self.player("ann")
        r = self.post(ann, "  Found the pond treasure!  ")
        self.assertEqual(r.status_code, 201)
        data = r.get_json()
        self.assertEqual((data["author"], data["text"], data["mine"], data["can_delete"]),
                         ("ann", "Found the pond treasure!", True, True))
        self.assertEqual((data["likes"], data["comment_count"], data["hunt"]), (0, 0, None))
        self.assertEqual(data["ago"], "Just now")

    def test_bad_posts_are_refused(self):
        ann = self.player("ann")
        for body in ({"text": ""}, {"text": "   "}, {}, {"text": "a" * 501}):
            with self.subTest(body=body):
                self.assertEqual(ann.post("/api/posts", json=body).status_code, 400)
        self.assertEqual(ann.post("/api/posts", data="hi", content_type="text/plain").status_code, 400)
        self.assertEqual(db.session.query(Post).count(), 0)

    def test_text_is_stored_as_typed_not_as_html(self):
        data = self.post(self.player("ann"), "<b>hi</b>").get_json()
        self.assertEqual(data["text"], "<b>hi</b>")  # the page shows it with textContent

    def test_everyone_sees_every_post_newest_first(self):
        ann, bob = self.player("ann"), self.player("bob")
        self.post(ann, "first")
        self.post(bob, "second")
        posts = self.feed(ann)["posts"]
        self.assertEqual([(p["author"], p["text"]) for p in posts], [("bob", "second"), ("ann", "first")])
        self.assertEqual([p["mine"] for p in posts], [False, True])

    def test_the_feed_comes_in_pages(self):
        ann = self.player("ann")
        for n in range(FEED_PAGE_SIZE + 3):
            self.post(ann, f"post {n}")
        first = self.feed(ann)
        self.assertEqual(len(first["posts"]), FEED_PAGE_SIZE)
        self.assertEqual(first["next_offset"], FEED_PAGE_SIZE)
        second = self.feed(ann, first["next_offset"])
        self.assertEqual([p["text"] for p in second["posts"]], ["post 2", "post 1", "post 0"])
        self.assertIsNone(second["next_offset"])

    def test_bad_offset(self):
        self.assertEqual(self.player("ann").get("/api/feed?offset=-3").status_code, 400)

    # ---------------------------------------------------------------- hunts on the feed

    def test_a_finished_hunt_shows_up_as_a_post(self):
        ann = self.player("ann")
        self.finish_hunt(ann, "Pond")
        posts = self.feed(self.player("bob"))["posts"]
        self.assertEqual(len(posts), 1)
        hunt = posts[0]["hunt"]
        self.assertEqual((posts[0]["author"], hunt["treasure"], hunt["distance_km"], hunt["time"]),
                         ("ann", "Pond", 0.75, "10:00"))
        self.assertEqual((hunt["steps"], hunt["calories"]), (1000, 24.4))

    def test_a_hunt_gets_only_one_post(self):
        ann = self.player("ann")
        self.finish_hunt(ann)
        self.feed(ann)
        self.feed(ann)
        self.assertEqual(db.session.query(Post).count(), 1)

    def test_hunt_posts_cannot_be_deleted(self):
        ann = self.player("ann")
        self.finish_hunt(ann)
        post = self.feed(ann)["posts"][0]
        self.assertFalse(post["can_delete"])
        self.assertEqual(ann.delete(f"/api/posts/{post['id']}").status_code, 403)

    # ---------------------------------------------------------------- likes

    def test_like_and_unlike(self):
        ann, bob = self.player("ann"), self.player("bob")
        pid = self.post(ann).get_json()["id"]
        r = bob.post(f"/api/posts/{pid}/like")
        self.assertEqual(r.get_json(), {"likes": 1, "liked_by_me": True, "like_summary": "You"})
        seen_by_ann = self.feed(ann)["posts"][0]
        self.assertEqual((seen_by_ann["likes"], seen_by_ann["liked_by_me"], seen_by_ann["like_summary"]),
                         (1, False, "bob"))
        r = bob.post(f"/api/posts/{pid}/like")  # again: takes it back
        self.assertEqual(r.get_json(), {"likes": 0, "liked_by_me": False, "like_summary": ""})
        self.assertEqual(db.session.query(PostLike).count(), 0)

    def test_likes_from_several_players(self):
        ann, bob, cyd = self.player("ann"), self.player("bob"), self.player("cyd")
        pid = self.post(ann).get_json()["id"]
        bob.post(f"/api/posts/{pid}/like")
        self.assertEqual(cyd.post(f"/api/posts/{pid}/like").get_json()["like_summary"], "You and bob")

    def test_liking_an_unknown_post_is_404(self):
        self.assertEqual(self.player("ann").post("/api/posts/999/like").status_code, 404)

    # ---------------------------------------------------------------- comments

    def test_comment_on_a_post(self):
        ann, bob = self.player("ann"), self.player("bob")
        pid = self.post(ann).get_json()["id"]
        r = bob.post(f"/api/posts/{pid}/comments", json={"text": " Nice find! "})
        self.assertEqual(r.status_code, 201)
        self.assertEqual((r.get_json()["author"], r.get_json()["text"], r.get_json()["mine"]),
                         ("bob", "Nice find!", True))
        bob.post(f"/api/posts/{pid}/comments", json={"text": "Second"})
        post = self.feed(ann)["posts"][0]
        self.assertEqual(post["comment_count"], 2)
        self.assertEqual([c["text"] for c in post["comments"]], ["Nice find!", "Second"])  # oldest first
        self.assertEqual([c["mine"] for c in post["comments"]], [False, False])

    def test_bad_comments_are_refused(self):
        ann = self.player("ann")
        pid = self.post(ann).get_json()["id"]
        self.assertEqual(ann.post(f"/api/posts/{pid}/comments", json={"text": ""}).status_code, 400)
        self.assertEqual(ann.post(f"/api/posts/{pid}/comments", json={"text": "a" * 301}).status_code, 400)
        self.assertEqual(ann.post("/api/posts/999/comments", json={"text": "hi"}).status_code, 404)

    def test_delete_only_your_own_comment(self):
        ann, bob = self.player("ann"), self.player("bob")
        pid = self.post(ann).get_json()["id"]
        cid = bob.post(f"/api/posts/{pid}/comments", json={"text": "hi"}).get_json()["id"]
        self.assertEqual(ann.delete(f"/api/comments/{cid}").status_code, 403)
        self.assertEqual(bob.delete(f"/api/comments/{cid}").status_code, 200)
        self.assertEqual(bob.delete(f"/api/comments/{cid}").status_code, 404)

    # ---------------------------------------------------------------- deleting posts

    def test_delete_only_your_own_post(self):
        ann, bob = self.player("ann"), self.player("bob")
        pid = self.post(ann).get_json()["id"]
        bob.post(f"/api/posts/{pid}/like")
        bob.post(f"/api/posts/{pid}/comments", json={"text": "hi"})
        self.assertEqual(bob.delete(f"/api/posts/{pid}").status_code, 403)
        self.assertEqual(ann.delete(f"/api/posts/{pid}").status_code, 200)
        self.assertEqual([db.session.query(m).count() for m in (Post, PostLike, PostComment)], [0, 0, 0])
        self.assertEqual(ann.delete(f"/api/posts/{pid}").status_code, 404)


if __name__ == "__main__":
    unittest.main()

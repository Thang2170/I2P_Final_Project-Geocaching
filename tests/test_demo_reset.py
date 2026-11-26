"""B: `python reset_demo.py` puts the demo back to the start of the story, keeping other players."""

import unittest

import reset_demo
from app import create_app
from coin_api import get_balance
from demo_content import DEMO_FULL_HUNT
from demo_data import seed_demo_story
from demo_extras import DEMO_WALKERS
from demo_reset import reset_demo as do_reset
from models import (CoinTransaction, Hunt, HuntMember, Journey, Post, PostLike, TrailWalk, TrailWalkDetail, Treasure,
                    User, ZoneBonus, db)


def user(name):
    return db.session.execute(db.select(User).filter_by(username=name)).scalar_one_or_none()


def count(model, *where):
    return db.session.execute(db.select(db.func.count()).select_from(model).where(*where)).scalar()


class ResetTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app("sqlite:///:memory:")
        self.context = self.app.app_context()
        self.context.push()
        seed_demo_story()
        self.fresh = self.snapshot()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
        self.context.pop()

    def snapshot(self):
        demo = user("demo_player")
        return {"balance": get_balance(demo.id), "journeys": count(Journey), "posts": count(Post),
                "treasures": sorted(db.session.execute(db.select(Treasure.name)).scalars()),
                "full_hunt_members": count(HuntMember, HuntMember.hunt_id == db.session.execute(
                    db.select(Hunt.id).where(Hunt.name == DEMO_FULL_HUNT["name"])).scalar())}

    def rehearse(self):
        """A messy rehearsal: demo_player earns and spends, hides a treasure, walks, posts;
        a teammate (zoe) likes demo_player's post and finds demo_player's treasure."""
        c = self.client
        c.post("/api/login", json={"username": "demo_player", "password": "demo1234"})
        c.post("/api/treasures", json={"name": "Stage spot", "description": "hidden on stage",
                                       "lat": 24.7900, "lon": 120.9900})
        demo = user("demo_player")
        spot = db.session.execute(db.select(Treasure).filter_by(name="Stage spot")).scalar_one()
        db.session.add(CoinTransaction(user_id=demo.id, amount=25, reason="found"))
        journey = Journey(user_id=demo.id, treasure_id=spot.id, distance_m=300, duration_s=240, steps=400, calories=15)
        db.session.add(journey)
        db.session.flush()
        db.session.add(ZoneBonus(journey_id=journey.id, user_id=demo.id, seconds=200, coins=1))
        post = Post(user_id=demo.id, text="On stage!")
        db.session.add(post)
        db.session.flush()
        walk = TrailWalk(user_id=demo.id, checkpoints=2, distance_m=500, duration_s=400, steps=600, calories=20, post_id=post.id)
        db.session.add(walk)
        db.session.flush()
        db.session.add(TrailWalkDetail(walk_id=walk.id, signature="loop:1-2", shape="loop", treasure_ids="[1, 2]", splits="[]"))
        db.session.commit()
        c.post("/api/register", json={"username": "zoe", "password": "secret1"})  # a teammate's own player
        zoe = user("zoe")
        db.session.add(PostLike(post_id=post.id, user_id=zoe.id))
        db.session.add(CoinTransaction(user_id=zoe.id, amount=10, reason="found", treasure_id=spot.id))
        db.session.add(CoinTransaction(user_id=zoe.id, amount=7, reason="gift"))
        db.session.add(Post(user_id=zoe.id, text="zoe's own post"))
        db.session.commit()
        c.post("/api/register", json={"username": "stage_kid", "password": "secret1"})  # registered on stage
        # someone joins the full demo hunt's line, as in the story
        db.session.add(HuntMember(hunt_id=db.session.execute(db.select(Hunt.id).filter_by(
            name=DEMO_FULL_HUNT["name"])).scalar(), user_id=user("stage_kid").id))
        db.session.commit()

    def test_back_to_the_start_of_the_story(self):
        self.rehearse()
        self.assertNotEqual(self.snapshot(), self.fresh)
        result = do_reset(["stage_kid"])
        self.assertEqual(sorted(result["removed"]),
                         sorted(["alice", "ben", "demo_player", "stage_kid", *DEMO_WALKERS]))  # B: + heat map walkers
        self.assertEqual(self.snapshot() | {"posts": None}, self.fresh | {"posts": None})
        self.assertEqual(count(Post), self.fresh["posts"] + 1)  # + zoe's own post
        self.assertIsNone(user("stage_kid"))
        self.assertEqual(count(TrailWalk) + count(TrailWalkDetail) + count(ZoneBonus), 0)
        self.assertEqual(count(PostLike, PostLike.user_id == user("zoe").id), 0)  # her like on a deleted post

    def test_other_players_are_kept(self):
        self.rehearse()
        zoe_id = user("zoe").id
        do_reset()
        self.assertIsNotNone(user("zoe"))
        self.assertEqual(get_balance(zoe_id), 7)  # her gift stays; the find of demo_player's treasure goes
        self.assertEqual(count(Post, Post.user_id == zoe_id), 1)

    def test_twice_in_a_row(self):
        do_reset()
        do_reset()
        self.assertEqual(self.snapshot(), self.fresh)

    def test_on_a_database_without_the_demo(self):
        empty = create_app("sqlite:///:memory:")  # never seeded
        with empty.app_context():
            self.assertEqual(do_reset()["removed"], [])
            self.assertIsNotNone(user("demo_player"))
            db.session.remove()
            db.drop_all()
            db.engine.dispose()

    def test_the_command(self):
        said = []
        self.assertEqual(reset_demo.main([], answer=lambda q: "n", say=said.append, flask_app=self.app), 1)
        self.assertIn("Nothing was changed.", said)
        self.rehearse()
        self.assertEqual(reset_demo.main(["--yes", "--also", "stage_kid"], say=said.append, flask_app=self.app), 0)
        self.assertTrue(any(line.startswith("Removed: ") and "stage_kid" in line for line in said))
        self.assertTrue(any("demo1234" in line for line in said))
        self.assertEqual(self.snapshot(), self.fresh | {"posts": self.fresh["posts"] + 1})


if __name__ == "__main__":
    unittest.main()

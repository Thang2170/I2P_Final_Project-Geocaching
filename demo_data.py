"""Save the demo story into the database (owner: B).

Safe to run again and again: it only adds what is missing and never changes or deletes anything.
What gets saved is listed in demo_content.py.
"""

from calculator import calories_from_distance, steps_from_distance
from demo_content import (DEMO_FULL_HUNT, DEMO_HUNT_REACTIONS, DEMO_JOURNEYS, DEMO_PASSWORD, DEMO_POSTS,
                          DEMO_TREASURES, DEMO_USERS, GIFT_REASON, TREASURE_CREATOR)
from models import (CoinTransaction, Hunt, HuntMember, Journey, Post, PostComment, PostLike, Profile, Treasure,
                    User, add_missing_hunt_posts, db)
from walk_input import DEFAULT_WEIGHT_KG


def _get_user(username):
    return db.session.execute(db.select(User).where(User.username == username)).scalar_one_or_none()


def seed_demo_story():
    """Add the demo users, treasures and hunt that are missing. Returns what was added."""
    added = {"users": [], "treasures": [], "hunts": [], "journeys": [], "posts": []}

    for spec in DEMO_USERS:
        if _get_user(spec["username"]) is not None:
            continue
        user = User(username=spec["username"])
        user.set_password(DEMO_PASSWORD)
        db.session.add(user)
        db.session.flush()  # gives the new user an id
        db.session.add(Profile(user_id=user.id, weight_kg=spec["weight_kg"]))
        if spec["coins"]:
            db.session.add(CoinTransaction(user_id=user.id, amount=spec["coins"], reason=GIFT_REASON))
        added["users"].append(user.username)

    creator = _get_user(TREASURE_CREATOR)
    for spec in DEMO_TREASURES:
        exists = db.session.execute(db.select(Treasure.id).where(Treasure.name == spec["name"])).first()
        if exists is None:
            db.session.add(Treasure(created_by=creator.id if creator else None, **spec))
            added["treasures"].append(spec["name"])

    hunt_name = DEMO_FULL_HUNT["name"]
    if db.session.execute(db.select(Hunt.id).where(Hunt.name == hunt_name)).first() is None:
        hunt = Hunt(name=hunt_name, description=DEMO_FULL_HUNT["description"],
                    capacity=DEMO_FULL_HUNT["capacity"])
        db.session.add(hunt)
        db.session.flush()
        for username in DEMO_FULL_HUNT["members"]:
            member = _get_user(username)
            if member is not None:
                db.session.add(HuntMember(hunt_id=hunt.id, user_id=member.id))
        added["hunts"].append(hunt_name)

    # Finished hunts (after the treasures exist). Steps and calories use the player's saved weight.
    for spec in DEMO_JOURNEYS:
        player = _get_user(spec["username"])
        treasure = db.session.execute(db.select(Treasure).where(Treasure.name == spec["treasure"])).scalar_one_or_none()
        if player is None or treasure is None:
            continue
        done = db.session.execute(db.select(Journey.id).where(
            Journey.user_id == player.id, Journey.treasure_id == treasure.id)).first()
        if done is not None:
            continue
        profile = db.session.get(Profile, player.id)
        weight = profile.weight_kg if profile else DEFAULT_WEIGHT_KG
        db.session.add(Journey(
            user_id=player.id, treasure_id=treasure.id, distance_m=spec["distance_m"],
            duration_s=spec["duration_s"], steps=steps_from_distance(spec["distance_m"]),
            calories=round(calories_from_distance(spec["distance_m"], weight), 1)))
        added["journeys"].append(f"{player.username} -> {treasure.name}")

    db.session.commit()

    # Community feed: the written posts, then likes and comments on a finished hunt.
    for spec in DEMO_POSTS:
        author = _get_user(spec["username"])
        if author is None:
            continue
        exists = db.session.execute(db.select(Post.id).where(
            Post.user_id == author.id, Post.text == spec["text"])).first()
        if exists is not None:
            continue
        post = Post(user_id=author.id, text=spec["text"])
        db.session.add(post)
        db.session.flush()
        _react(post, spec)
        added["posts"].append(f"{author.username}: {spec['text'][:30]}")

    add_missing_hunt_posts()
    for spec in DEMO_HUNT_REACTIONS:
        post = _hunt_post(spec["username"], spec["treasure"])
        if post is None or _has_reactions(post):
            continue  # already done (or the hunt is missing)
        _react(post, spec)
        added["posts"].append(f"reactions on {spec['username']} -> {spec['treasure']}")

    db.session.commit()
    return added


def _react(post, spec):
    """Add the likes and comments listed in spec to post."""
    for name in spec["likes"]:
        fan = _get_user(name)
        if fan is not None:
            db.session.add(PostLike(post_id=post.id, user_id=fan.id))
    for name, text in spec["comments"]:
        writer = _get_user(name)
        if writer is not None:
            db.session.add(PostComment(post_id=post.id, user_id=writer.id, text=text))


def _hunt_post(username, treasure_name):
    """The post made by username's finished hunt to the named treasure, or None."""
    query = (db.select(Post).join(Journey, Post.journey_id == Journey.id)
             .join(User, Journey.user_id == User.id).join(Treasure, Journey.treasure_id == Treasure.id)
             .where(User.username == username, Treasure.name == treasure_name))
    return db.session.execute(query).scalar_one_or_none()


def _has_reactions(post):
    liked = db.session.execute(db.select(PostLike.id).where(PostLike.post_id == post.id).limit(1)).first()
    commented = db.session.execute(db.select(PostComment.id).where(PostComment.post_id == post.id).limit(1)).first()
    return liked is not None or commented is not None

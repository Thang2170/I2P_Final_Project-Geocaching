"""Save the demo story into the database (owner: B).

Safe to run again and again: it only adds what is missing and never changes or deletes anything.
What gets saved is listed in demo_content.py.
"""

from calculator import calories_from_distance, steps_from_distance
from demo_content import (DEMO_CHAT, DEMO_CHAT_HUNT, DEMO_FIND_COINS, DEMO_FRIEND_REQUESTS, DEMO_FRIENDS, DEMO_FULL_HUNT,
                          DEMO_HUNT_REACTIONS, DEMO_JOURNEYS, DEMO_PASSWORD, DEMO_POSTS, DEMO_RATINGS, DEMO_REPLIES,
                          DEMO_SHARES, DEMO_TOUR_SEEN, DEMO_TREASURES, DEMO_USERS, GIFT_REASON, TREASURE_CREATOR)
from friends import ACCEPTED, PENDING
from models import (CoinTransaction, CommentReply, Friendship, Hunt, HuntMember, HuntMessage, Journey, Notification,
                    Post, PostComment, PostLike, PostShare, Profile, TourSeen, Treasure, TreasureRating, User,
                    add_missing_hunt_posts, db)
from notify_rules import FRIEND_REQUEST
from onboarding import SKIPPED
from walk_input import DEFAULT_WEIGHT_KG


def _get_user(username):
    return db.session.execute(db.select(User).where(User.username == username)).scalar_one_or_none()


def seed_demo_story():
    """Add the demo users, treasures and hunt that are missing. Returns what was added."""
    added = {"users": [], "treasures": [], "hunts": [], "journeys": [], "posts": [], "chat": [], "social": []}

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
        when = _hours_ago(spec.get("hours_ago", 0))
        db.session.add(Journey(
            user_id=player.id, treasure_id=treasure.id, distance_m=spec["distance_m"],
            duration_s=spec["duration_s"], steps=steps_from_distance(spec["distance_m"]),
            calories=round(calories_from_distance(spec["distance_m"], weight), 1), created_at=when))
        # B: a walk to a treasure ends with finding it, so the coins and "found" count agree
        db.session.add(CoinTransaction(user_id=player.id, amount=DEMO_FIND_COINS, reason="found_treasure",
                                       treasure_id=treasure.id, created_at=when))
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
        post = Post(user_id=author.id, text=spec["text"], created_at=_hours_ago(spec.get("hours_ago", 0)))
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

    added["chat"] = _seed_chat()
    added["social"] = _seed_social()

    for username in DEMO_TOUR_SEEN:  # no tour popping up mid-demo
        player = _get_user(username)
        if player is not None and db.session.get(TourSeen, player.id) is None:
            db.session.add(TourSeen(user_id=player.id, how=SKIPPED))

    db.session.commit()
    from demo_extras import seed_demo_extras  # B: heat map walkers, a race replay, rain / night treasures
    added["extras"] = seed_demo_extras()
    return added


def _seed_social():
    """Ratings, friends, a share and a reply (B: social features). Returns what was added."""
    added = []
    for username, treasure_name, stars in DEMO_RATINGS:
        player = _get_user(username)
        treasure = db.session.execute(db.select(Treasure).where(Treasure.name == treasure_name)).scalar_one_or_none()
        if player is None or treasure is None:
            continue
        rated = db.session.execute(db.select(TreasureRating.id).where(
            TreasureRating.user_id == player.id, TreasureRating.treasure_id == treasure.id)).first()
        if rated is None:
            db.session.add(TreasureRating(user_id=player.id, treasure_id=treasure.id, stars=stars))
            added.append(f"{username} rated {treasure_name} {stars} stars")

    for pairs, status in ((DEMO_FRIENDS, ACCEPTED), (DEMO_FRIEND_REQUESTS, PENDING)):
        for asker_name, other_name in pairs:
            asker, other = _get_user(asker_name), _get_user(other_name)
            if asker is None or other is None or _pair(asker.id, other.id) is not None:
                continue
            db.session.add(Friendship(requester_id=asker.id, addressee_id=other.id, status=status))
            if status == PENDING:
                db.session.add(Notification(user_id=other.id, kind=FRIEND_REQUEST, actor_id=asker.id))
            added.append(f"{asker_name} {'and' if status == ACCEPTED else 'asked'} {other_name}")
    db.session.flush()

    for spec in DEMO_SHARES:
        sharer, author = _get_user(spec["username"]), _get_user(spec["post_by"])
        if sharer is None or author is None:
            continue
        original = db.session.execute(db.select(Post).where(
            Post.user_id == author.id, Post.text.startswith(spec["post_starts"])).limit(1)).scalar_one_or_none()
        if original is None:
            continue
        done = db.session.execute(db.select(PostShare.id).join(Post, PostShare.post_id == Post.id).where(
            PostShare.original_id == original.id, Post.user_id == sharer.id)).first()
        if done is not None:
            continue
        share = Post(user_id=sharer.id, text=spec["text"], created_at=_hours_ago(spec.get("hours_ago", 0)))
        db.session.add(share)
        db.session.flush()
        db.session.add(PostShare(post_id=share.id, original_id=original.id))
        added.append(f"{spec['username']} shared {spec['post_by']}'s post")

    for replier_name, commenter_name, comment_starts, text in DEMO_REPLIES:
        replier, commenter = _get_user(replier_name), _get_user(commenter_name)
        if replier is None or commenter is None:
            continue
        comment = db.session.execute(db.select(PostComment).where(
            PostComment.user_id == commenter.id, PostComment.text.startswith(comment_starts)).limit(1)
        ).scalar_one_or_none()
        if comment is None:
            continue
        done = db.session.execute(db.select(CommentReply.id).where(
            CommentReply.comment_id == comment.id, CommentReply.user_id == replier.id)).first()
        if done is None:
            db.session.add(CommentReply(comment_id=comment.id, user_id=replier.id, text=text))
            added.append(f"{replier_name} replied to {commenter_name}")
    return added


def _pair(a_id, b_id):
    return db.session.execute(db.select(Friendship.id).where(db.or_(
        db.and_(Friendship.requester_id == a_id, Friendship.addressee_id == b_id),
        db.and_(Friendship.requester_id == b_id, Friendship.addressee_id == a_id)))).first()


def _seed_chat():
    """alice and ben join the everyday demo hunt and say a few things. Returns what was added."""
    added = []
    hunt = db.session.execute(db.select(Hunt).where(Hunt.name == DEMO_CHAT_HUNT)).scalar_one_or_none()
    if hunt is None:
        return added
    for username in DEMO_CHAT["members"]:
        member = _get_user(username)
        if member is None:
            continue
        joined = db.session.execute(db.select(HuntMember.id).where(
            HuntMember.hunt_id == hunt.id, HuntMember.user_id == member.id)).first()
        if joined is None:
            db.session.add(HuntMember(hunt_id=hunt.id, user_id=member.id))
            added.append(f"{username} joined {hunt.name}")
    has_messages = db.session.execute(
        db.select(HuntMessage.id).where(HuntMessage.hunt_id == hunt.id).limit(1)).first()
    if has_messages is None:
        for username, text in DEMO_CHAT["messages"]:
            writer = _get_user(username)
            if writer is not None:
                db.session.add(HuntMessage(hunt_id=hunt.id, user_id=writer.id, text=text))
        added.append(f"{len(DEMO_CHAT['messages'])} messages in {hunt.name}")
    return added


def _hours_ago(hours):
    """B: a time `hours` ago, as the naive UTC the database keeps."""
    from datetime import datetime, timedelta, timezone
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).replace(tzinfo=None)


def _react(post, spec):
    """Add the likes and comments listed in spec to post."""
    for name in spec["likes"]:
        fan = _get_user(name)
        if fan is not None:
            db.session.add(PostLike(post_id=post.id, user_id=fan.id))
    from datetime import timedelta
    for i, (name, text) in enumerate(spec["comments"], start=1):
        writer = _get_user(name)
        if writer is not None:
            # B: comments come after the post, half an hour apart (never in the future)
            when = min((post.created_at or _hours_ago(0)) + timedelta(minutes=30 * i), _hours_ago(0))
            db.session.add(PostComment(post_id=post.id, user_id=writer.id, text=text, created_at=when))


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

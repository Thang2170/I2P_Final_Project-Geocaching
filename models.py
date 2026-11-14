"""Database tables for the treasure hunt. Owner: B.

Flask-SQLAlchemy turns each class below into a table in a SQLite file.
Every db.Column attribute becomes a column in that table.
"""

from datetime import datetime, timezone

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import validates
from werkzeug.security import check_password_hash, generate_password_hash

from hunt_input import DEFAULT_CAPACITY, MAX_CAPACITY, MIN_CAPACITY
from walk_input import MAX_WEIGHT_KG, MIN_WEIGHT_KG

db = SQLAlchemy()

# The treasure that is saved on the very first run, so the map is never empty.
DEMO_TREASURE = {
    "name": "National Tsing Hua University",
    "description": "Demo treasure. Find it on the NTHU campus.",
    "lat": 24.795324,
    "lon": 120.994796,
}


def _utcnow():
    return datetime.now(timezone.utc)


class User(db.Model):
    """A player. Weight lives in Profile; coins come in a later week."""

    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    # Only a scrambled (hashed) copy of the password is ever stored, never the password itself.
    password_hash = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)

    # user.treasures gives every treasure this player uploaded
    treasures = db.relationship("Treasure", back_populates="creator")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return self.password_hash is not None and check_password_hash(self.password_hash, password)

    def to_dict(self):
        """Safe to send to the browser: never includes the password hash."""
        return {"id": self.id, "username": self.username}


class Profile(db.Model):
    """Extra facts about a player. One row per user who has saved something.

    A separate table (instead of a new User column) so databases that already
    exist pick it up automatically: db.create_all() adds new tables but never
    changes old ones.
    """

    __tablename__ = "profiles"

    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), primary_key=True)
    weight_kg = db.Column(db.Float, nullable=True)  # used to estimate calories

    @validates("weight_kg")
    def _check_weight(self, key, value):
        if value is not None and not MIN_WEIGHT_KG <= value <= MAX_WEIGHT_KG:
            raise ValueError(f"weight_kg must be between {MIN_WEIGHT_KG} and {MAX_WEIGHT_KG}")
        return value


class Treasure(db.Model):
    """A hidden treasure at a real place."""

    __tablename__ = "treasures"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False, default="")
    lat = db.Column(db.Float, nullable=False)  # latitude in degrees
    lon = db.Column(db.Float, nullable=False)  # longitude in degrees
    # Who uploaded it. Empty (None) for the built-in demo treasure.
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)

    # treasure.creator gives the User who uploaded it
    creator = db.relationship("User", back_populates="treasures")

    @validates("lat")
    def _check_lat(self, key, value):
        if value is not None and not -90 <= value <= 90:
            raise ValueError("lat must be between -90 and 90")
        return value

    @validates("lon")
    def _check_lon(self, key, value):
        if value is not None and not -180 <= value <= 180:
            raise ValueError("lon must be between -180 and 180")
        return value

    def to_dict(self):
        """Plain dict, ready for jsonify() or for a template."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "lat": self.lat,
            "lon": self.lon,
        }


class CoinTransaction(db.Model):
    """One line in a player's coin ledger: coins earned (+) or spent (-).

    A player's balance is the sum of their amounts. Keeping every change as its
    own row means nothing is ever overwritten, and the shop can later add
    negative rows for purchases.
    """

    __tablename__ = "coin_transactions"
    # A player can be paid for a treasure only once. (Rows with no treasure, such as
    # shop purchases, are not limited: SQL treats each empty value as different.)
    __table_args__ = (db.UniqueConstraint("user_id", "treasure_id", name="one_payment_per_treasure"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    amount = db.Column(db.Integer, nullable=False)       # + earned, - spent
    reason = db.Column(db.String(30), nullable=False)    # "found_treasure", later "shop"
    treasure_id = db.Column(db.Integer, db.ForeignKey("treasures.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)


class Purchase(db.Model):
    """Something a player bought in the shop.

    The coins it cost are a separate negative row in CoinTransaction, saved in the
    same commit, so the balance and the purchase list can never disagree.
    """

    __tablename__ = "purchases"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    item_id = db.Column(db.String(50), nullable=False)    # an id from shop.ITEMS
    price = db.Column(db.Integer, nullable=False)         # what it cost at the time
    voucher_code = db.Column(db.String(20), unique=True, nullable=True)  # vouchers only
    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)


class Hunt(db.Model):
    """A group hunt that players can join (Feature 8). Extra players wait in line."""

    __tablename__ = "hunts"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(60), nullable=False)
    description = db.Column(db.Text, nullable=False, default="")
    capacity = db.Column(db.Integer, nullable=False, default=DEFAULT_CAPACITY)  # players at once
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)  # None: demo hunt
    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)

    @validates("capacity")
    def _check_capacity(self, key, value):
        if value is not None and not MIN_CAPACITY <= value <= MAX_CAPACITY:
            raise ValueError(f"capacity must be between {MIN_CAPACITY} and {MAX_CAPACITY}")
        return value


class HuntMember(db.Model):
    """A player who joined a hunt. The id order is the order they joined."""

    __tablename__ = "hunt_members"
    __table_args__ = (db.UniqueConstraint("hunt_id", "user_id", name="one_place_per_player"),)

    id = db.Column(db.Integer, primary_key=True)
    hunt_id = db.Column(db.Integer, db.ForeignKey("hunts.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    joined_at = db.Column(db.DateTime, default=_utcnow, nullable=False)


def seed_demo_hunt():
    """Save a demo hunt if there are no hunts yet, so the Hunts page is never empty."""
    if db.session.execute(db.select(Hunt.id).limit(1)).first() is None:
        db.session.add(Hunt(name="NTHU campus walk", capacity=5,
                            description="Demo hunt. Join, then explore the campus together."))
        db.session.commit()


def seed_demo_data():
    """Save the demo treasure if there are no treasures yet.

    Safe to call every time the app starts: it never adds duplicates.
    """
    first_treasure = db.session.execute(db.select(Treasure.id).limit(1)).first()
    if first_treasure is None:
        db.session.add(Treasure(**DEMO_TREASURE))
        db.session.commit()


class Journey(db.Model):
    """A finished hunt: a player walked to a treasure and reached it.

    Saved once per player and treasure. Steps and calories are worked out by Python from the
    distance and the player's weight when the hunt is saved, never taken from the browser.
    """

    __tablename__ = "journeys"
    __table_args__ = (db.UniqueConstraint("user_id", "treasure_id", name="one_journey_per_treasure"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    treasure_id = db.Column(db.Integer, db.ForeignKey("treasures.id"), nullable=False)
    distance_m = db.Column(db.Float, nullable=False)
    duration_s = db.Column(db.Integer, nullable=False)
    steps = db.Column(db.Integer, nullable=False)
    calories = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)

    user = db.relationship("User")
    treasure = db.relationship("Treasure")


class Post(db.Model):
    """One post on the Community feed.

    A player writes it, or it is made automatically when a hunt is finished
    (then journey_id points at that hunt and text may be empty).
    """

    __tablename__ = "posts"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    text = db.Column(db.Text, nullable=False, default="")
    # A finished hunt gets exactly one post, so the unique rule stops doubles.
    journey_id = db.Column(db.Integer, db.ForeignKey("journeys.id"), unique=True, nullable=True)
    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)

    user = db.relationship("User")
    journey = db.relationship("Journey")


class PostLike(db.Model):
    """A player liked a post. Liking again removes the like."""

    __tablename__ = "post_likes"
    __table_args__ = (db.UniqueConstraint("post_id", "user_id", name="one_like_per_player"),)

    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey("posts.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)

    user = db.relationship("User")


class PostComment(db.Model):
    """A comment under a post."""

    __tablename__ = "post_comments"

    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey("posts.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    text = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)

    user = db.relationship("User")


def add_missing_hunt_posts():
    """Give every finished hunt its post on the Community feed. Returns how many were added.

    Hunts saved before the feed existed get one too. The post keeps the time of the hunt,
    so it sits in the right place in the feed. Safe to call every time.
    """
    query = (db.select(Journey).outerjoin(Post, Post.journey_id == Journey.id)
             .where(Post.id.is_(None)))
    missing = db.session.execute(query).scalars().all()
    for journey in missing:
        db.session.add(Post(user_id=journey.user_id, journey_id=journey.id, text="",
                            created_at=journey.created_at))
    if missing:
        db.session.commit()
    return len(missing)

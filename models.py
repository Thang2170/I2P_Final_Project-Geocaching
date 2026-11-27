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


class TourSeen(db.Model):
    """A player has seen the first-time tour, so it doesn't pop up again by itself.

    A separate table (instead of a new User column) so existing databases pick it up.
    """

    __tablename__ = "tour_seen"

    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), primary_key=True)
    how = db.Column(db.String(10), nullable=False)  # "finished" or "skipped" (see onboarding.py)
    seen_at = db.Column(db.DateTime, default=_utcnow, nullable=False)


class HuntMessage(db.Model):
    """One message in a hunt's group chat. The id order is the order they were sent."""

    __tablename__ = "hunt_messages"

    id = db.Column(db.Integer, primary_key=True)
    hunt_id = db.Column(db.Integer, db.ForeignKey("hunts.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    text = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)

    user = db.relationship("User")


class ChatRead(db.Model):
    """The newest group-chat message a player has seen in a hunt, for the unread count."""

    __tablename__ = "chat_reads"
    __table_args__ = (db.UniqueConstraint("user_id", "hunt_id", name="one_read_mark_per_chat"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    hunt_id = db.Column(db.Integer, db.ForeignKey("hunts.id"), nullable=False)
    last_read_id = db.Column(db.Integer, nullable=False, default=0)


class Notification(db.Model):
    """Something for the bell in the top bar: a like, a comment, or "you moved up".

    The words are not stored; notify_rules.py writes them when the bell is opened.
    """

    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)  # who gets it
    kind = db.Column(db.String(20), nullable=False)  # see notify_rules.KINDS
    actor_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)  # who did it
    post_id = db.Column(db.Integer, db.ForeignKey("posts.id"), nullable=True)
    hunt_id = db.Column(db.Integer, db.ForeignKey("hunts.id"), nullable=True)
    seen = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)

    actor = db.relationship("User", foreign_keys=[actor_id])


class TreasureRating(db.Model):
    """A player's 1-5 star rating of a treasure they found. One per player and treasure; can be changed."""

    __tablename__ = "treasure_ratings"
    __table_args__ = (db.UniqueConstraint("user_id", "treasure_id", name="one_rating_per_treasure"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    treasure_id = db.Column(db.Integer, db.ForeignKey("treasures.id"), nullable=False, index=True)
    stars = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow, nullable=False)


class Friendship(db.Model):
    """Two players who are friends, or one asked the other (owner: B). Rules: friends.py.

    One row per pair: whoever asked first is the requester. A new table (not new columns),
    so nobody has to delete their database.
    """

    __tablename__ = "friendships"
    __table_args__ = (db.UniqueConstraint("requester_id", "addressee_id", name="one_request_per_pair"),)

    id = db.Column(db.Integer, primary_key=True)
    requester_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    addressee_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    status = db.Column(db.String(10), nullable=False, default="pending")  # friends.PENDING / ACCEPTED
    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)
    answered_at = db.Column(db.DateTime, nullable=True)


class PostShare(db.Model):
    """A post that shares another post (owner: B). Rules: shares.py.

    The share is a normal Post (its own words, likes and comments); this row says which post
    it shares. original_id becomes empty when the original is deleted: the feed then says
    "This post was deleted". A new table (not a new column on posts).
    """

    __tablename__ = "post_shares"

    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey("posts.id"), unique=True, nullable=False)  # the share
    original_id = db.Column(db.Integer, db.ForeignKey("posts.id"), nullable=True, index=True)
    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)


class CommentReply(db.Model):
    """A reply to a comment, shown indented under it (owner: B).

    A new table, not a new column on post_comments, so nobody has to delete their database.
    """

    __tablename__ = "comment_replies"

    id = db.Column(db.Integer, primary_key=True)
    comment_id = db.Column(db.Integer, db.ForeignKey("post_comments.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    text = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)

    user = db.relationship("User")


class WalkPoint(db.Model):
    """One GPS point of a player's recent trail, for "prove you walked" (owner: B). Rules: walk_proof.py.

    Only the last 30 minutes are kept; older points are deleted as new ones arrive.
    """

    __tablename__ = "walk_points"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    lat = db.Column(db.Float, nullable=False)
    lon = db.Column(db.Float, nullable=False)
    at = db.Column(db.DateTime, default=_utcnow, nullable=False)


class FindCheck(db.Model):
    """A find whose GPS trail looked faked, waiting for an admin (owner: B). Rules: walk_proof.py.

    decision: None (waiting), "kept" (it was fine) or "reversed" (the coins were taken back).
    """

    __tablename__ = "find_checks"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    treasure_id = db.Column(db.Integer, db.ForeignKey("treasures.id"), nullable=False)
    reasons = db.Column(db.String(100), nullable=False)  # e.g. "teleport,no_walk"
    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)
    decision = db.Column(db.String(10), nullable=True)
    decided_at = db.Column(db.DateTime, nullable=True)

    user = db.relationship("User", foreign_keys=[user_id])
    treasure = db.relationship("Treasure")


class RiddleChain(db.Model):
    """A riddle chain: treasures found in order, each riddle unlocking the next (owner: B). Rules: riddles.py."""

    __tablename__ = "riddle_chains"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(60), nullable=False)
    creator_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)

    creator = db.relationship("User")
    steps = db.relationship("RiddleStep", order_by="RiddleStep.position", cascade="all, delete-orphan")


class RiddleStep(db.Model):
    """One step of a riddle chain: the treasure and the riddle that leads to it."""

    __tablename__ = "riddle_steps"

    id = db.Column(db.Integer, primary_key=True)
    chain_id = db.Column(db.Integer, db.ForeignKey("riddle_chains.id"), nullable=False, index=True)
    position = db.Column(db.Integer, nullable=False)  # 1, 2, 3, ...
    treasure_id = db.Column(db.Integer, db.ForeignKey("treasures.id"), nullable=False, index=True)
    clue = db.Column(db.String(200), nullable=False)

    treasure = db.relationship("Treasure")


class ChainBonus(db.Model):
    """A player finished a riddle chain and was paid its bonus (once per chain)."""

    __tablename__ = "chain_bonuses"
    __table_args__ = (db.UniqueConstraint("user_id", "chain_id", name="one_bonus_per_chain"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    chain_id = db.Column(db.Integer, db.ForeignKey("riddle_chains.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)


class ChallengeClaim(db.Model):
    """A weekly challenge a player finished and was paid for (owner: B). Rules: streaks.py.

    week_start is the Monday (Taiwan time) of that week, so each challenge pays once a week.
    """

    __tablename__ = "challenge_claims"
    __table_args__ = (db.UniqueConstraint("user_id", "week_start", "challenge_id", name="one_claim_per_week"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    week_start = db.Column(db.Date, nullable=False)
    challenge_id = db.Column(db.String(20), nullable=False)
    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)


class TeamChoice(db.Model):
    """Which team a player walks for in "claim the campus" (owner: B). Rules: territory.py."""

    __tablename__ = "team_choices"

    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), primary_key=True)
    team = db.Column(db.String(10), nullable=False)
    chosen_at = db.Column(db.DateTime, default=_utcnow, nullable=False)


class HexVisit(db.Model):
    """A player walked through a hexagon on a day, for a team (owner: B). Rules: territory.py.

    One row per player, hexagon and day, so standing still all day still counts once.
    The team is saved with the visit: switching team later doesn't move old visits.
    """

    __tablename__ = "hex_visits"
    __table_args__ = (db.UniqueConstraint("user_id", "day", "q", "r", name="one_visit_per_day"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    team = db.Column(db.String(10), nullable=False)
    q = db.Column(db.Integer, nullable=False)
    r = db.Column(db.Integer, nullable=False)
    day = db.Column(db.Date, nullable=False)                   # Taiwan date
    week_start = db.Column(db.Date, nullable=False, index=True)  # its Monday


class BodyHeight(db.Model):
    """A player's height, for their own step length (owner: B). Rules: walk_input.py.

    A new table, not a new column on profiles, so nobody has to delete their database.
    """

    __tablename__ = "body_heights"

    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), primary_key=True)
    height_cm = db.Column(db.Float, nullable=False)


class ZoneBonus(db.Model):
    """Bonus coins for time in the 60-80% heart-rate zone, paid once per saved hunt (owner: B).

    Rules: zone_coach.py. A new table, so nobody has to delete their database.
    """

    __tablename__ = "zone_bonuses"

    journey_id = db.Column(db.Integer, db.ForeignKey("journeys.id"), primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    seconds = db.Column(db.Integer, nullable=False)   # time in the bonus zone
    coins = db.Column(db.Integer, nullable=False)     # may be 0
    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)


class CooldownDone(db.Model):
    """A finished cool-down quest after a hunt, paid once per hunt (owner: B). Rules: zone_coach.py."""

    __tablename__ = "cooldowns_done"

    journey_id = db.Column(db.Integer, db.ForeignKey("journeys.id"), primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)


class GoalChoice(db.Model):
    """The health goal a player picked: steps, active or rehab (owner: B). Rules: goals.py."""

    __tablename__ = "goal_choices"

    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), primary_key=True)
    goal = db.Column(db.String(10), nullable=False)
    started_on = db.Column(db.Date, nullable=False)   # Taiwan date: rehab grows week by week from here


class GoalMilestone(db.Model):
    """A milestone a player collected, once per day or week (owner: B). Rules: goals.py."""

    __tablename__ = "goal_milestones"
    __table_args__ = (db.UniqueConstraint("user_id", "milestone_id", "period_start", name="one_milestone_per_period"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    milestone_id = db.Column(db.String(20), nullable=False)
    period_start = db.Column(db.Date, nullable=False)  # the day, or the Monday of the week
    coins = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)


class WalkMode(db.Model):
    """The walking mode a player picked: normal, tryhard or calm (owner: B). Rules: modes.py."""

    __tablename__ = "walk_modes"

    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), primary_key=True)
    mode = db.Column(db.String(10), nullable=False)


class ModeBonus(db.Model):
    """A try-hard or calm bonus, paid once per saved hunt (owner: B). Rules: modes.py."""

    __tablename__ = "mode_bonuses"

    journey_id = db.Column(db.Integer, db.ForeignKey("journeys.id"), primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    mode = db.Column(db.String(10), nullable=False)
    coins = db.Column(db.Integer, nullable=False)   # may be 0 (the pace was too slow)
    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)


class SafetyAlert(db.Model):
    """A hunt the band's readings stopped: low SpO2 or an abnormal heart rate (owner: B).

    Rules: safety.py. Kept so the player (and the Health page later) can see it happened.
    """

    __tablename__ = "safety_alerts"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    reason = db.Column(db.String(20), nullable=False)    # low_spo2, high_hr or low_hr
    title = db.Column(db.String(80), nullable=False)
    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)


class StreakFreeze(db.Model):
    """A streak freeze a player bought; used_on is the missed day it covered (owner: B). Rules: habits.py."""

    __tablename__ = "streak_freezes"
    __table_args__ = (db.UniqueConstraint("user_id", "used_on", name="one_freeze_per_day"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    bought_on = db.Column(db.Date, nullable=False)    # Taiwan date
    used_on = db.Column(db.Date, nullable=True)       # empty until it covers a missed day


class StreakShare(db.Model):
    """A streak shared to the Community, once a day (owner: B). Rules: habits.py."""

    __tablename__ = "streak_shares"
    __table_args__ = (db.UniqueConstraint("user_id", "day", name="one_streak_share_per_day"),)

    post_id = db.Column(db.Integer, db.ForeignKey("posts.id"), primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    day = db.Column(db.Date, nullable=False)
    streak = db.Column(db.Integer, nullable=False)


class TrailWalk(db.Model):
    """A Treasure Trail walked with the live panel, saved at the finish (owner: B).

    Rules: trail_planner.py. A new table, so nobody has to delete their database.
    """

    __tablename__ = "trail_walks"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    checkpoints = db.Column(db.Integer, nullable=False)
    distance_m = db.Column(db.Float, nullable=False)
    duration_s = db.Column(db.Integer, nullable=False)
    steps = db.Column(db.Integer, nullable=False)
    calories = db.Column(db.Float, nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey("posts.id"), nullable=True)  # its Community post
    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)


class ActiveTrail(db.Model):
    """A timed Treasure Trail in progress, so it survives a reload or a lost phone (owner: B).

    One row per player at most. The state (checkpoints, splits...) is checked by
    trail_planner.parse_active_trail and kept as JSON. A new table: no database to delete.
    """

    __tablename__ = "active_trails"

    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), primary_key=True)
    state = db.Column(db.Text, nullable=False)       # JSON from parse_active_trail
    updated_at = db.Column(db.DateTime, nullable=False)


class TrailWalkDetail(db.Model):
    """More about a saved trail walk: which trail it was and the split times (owner: B).

    Kept beside trail_walks (a new table, not new columns), so personal bests can be found:
    walks with the same signature are the same trail. Rules: trail_planner.py.
    """

    __tablename__ = "trail_walk_details"

    walk_id = db.Column(db.Integer, db.ForeignKey("trail_walks.id"), primary_key=True)
    signature = db.Column(db.String(200), nullable=True, index=True)  # e.g. "loop:3-7-12"
    shape = db.Column(db.String(10), nullable=False)
    treasure_ids = db.Column(db.Text, nullable=False)                 # JSON list, in walking order
    splits = db.Column(db.Text, nullable=False)                       # JSON list of seconds


class StreakReminder(db.Model):
    """The evening "streak at risk" check, once a day per player (owner: B). Rules: habits.py.

    A row means "checked today"; notification_id is set if the bell was told. Keeping the streak
    and freezes of that moment lets the bell's words stay the same later.
    """

    __tablename__ = "streak_reminders"
    __table_args__ = (db.UniqueConstraint("user_id", "day", name="one_streak_check_per_day"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    day = db.Column(db.Date, nullable=False)                 # Taiwan date
    streak = db.Column(db.Integer, nullable=False)
    freezes = db.Column(db.Integer, nullable=False)
    notification_id = db.Column(db.Integer, db.ForeignKey("notifications.id"), nullable=True, index=True)


class ReportShare(db.Model):
    """A weekly report shared to the Community, once per week (owner: B). Rules: weekly_report.py."""

    __tablename__ = "report_shares"
    __table_args__ = (db.UniqueConstraint("user_id", "week_start", name="one_report_share_per_week"),)

    post_id = db.Column(db.Integer, db.ForeignKey("posts.id"), primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    week_start = db.Column(db.Date, nullable=False)  # the Monday (Taiwan time)


class TreasureReport(db.Model):
    """B: "I couldn't find it": one player looked at a treasure and it wasn't there (dnf.py).

    Only reports after the treasure's last find count, so a find clears them without deleting.
    """

    __tablename__ = "treasure_reports"
    id = db.Column(db.Integer, primary_key=True)
    treasure_id = db.Column(db.Integer, db.ForeignKey("treasures.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)


class MissingAlert(db.Model):
    """B: the owner was told their treasure may be missing (which notification, for the bell)."""

    __tablename__ = "missing_alerts"
    id = db.Column(db.Integer, primary_key=True)
    treasure_id = db.Column(db.Integer, db.ForeignKey("treasures.id"), nullable=False)
    count = db.Column(db.Integer, nullable=False)  # how many players had reported it
    notification_id = db.Column(db.Integer, db.ForeignKey("notifications.id"), nullable=True, index=True)
    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)


class RacePoint(db.Model):
    """B: where a player was during a hunt race, kept for the replay (replay.py).

    Its own table because the walk-proof trail (WalkPoint) forgets points after 30 minutes.
    """

    __tablename__ = "race_points"
    id = db.Column(db.Integer, primary_key=True)
    hunt_id = db.Column(db.Integer, db.ForeignKey("hunts.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    lat = db.Column(db.Float, nullable=False)
    lon = db.Column(db.Float, nullable=False)
    at = db.Column(db.DateTime, default=_utcnow, nullable=False)


class TreasureCondition(db.Model):
    """B: a treasure that only appears in the rain or after dark (conditions.py).

    No row means it is an ordinary treasure that is always there.
    """

    __tablename__ = "treasure_conditions"
    treasure_id = db.Column(db.Integer, db.ForeignKey("treasures.id"), primary_key=True)
    condition = db.Column(db.String(10), nullable=False)  # conditions.RAIN or conditions.NIGHT


class RouteAccess(db.Model):
    """B: a player who wants step-free (wheelchair) routes (route_access.py). No row: walking."""

    __tablename__ = "route_access"
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), primary_key=True)
    access = db.Column(db.String(12), nullable=False)


class HeatVisit(db.Model):
    """B: a player walked through this 40 m hexagon on this day, for the heat map (heatmap.py).

    Kept for heatmap.KEEP_DAYS days, then deleted. The map only shows hexagons that
    heatmap.MIN_PLAYERS different players walked through, never one player's own path.
    """

    __tablename__ = "heat_visits"
    __table_args__ = (db.UniqueConstraint("user_id", "day", "q", "r", name="one_heat_visit_per_day"),)
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    q = db.Column(db.Integer, nullable=False)
    r = db.Column(db.Integer, nullable=False)
    day = db.Column(db.Date, nullable=False, index=True)  # Taiwan date


class LoginFailure(db.Model):
    """B: one wrong password, so guessing can be slowed down (login_guard.py).

    Rows older than login_guard.WINDOW_S are deleted on the next try; a right password clears them.
    """

    __tablename__ = "login_failures"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), nullable=False, index=True)  # as typed, in lower case
    place = db.Column(db.String(64), nullable=False)                   # the address the try came from
    at = db.Column(db.DateTime, default=_utcnow, nullable=False)


# ---------------------------------------------------------------- B: six new ways to play


class TreasureBox(db.Model):
    """B: a real box at a treasure that shows a code changing every 30 s (box_code.py).

    The secret is shown once, when the box is made, to put in the ESP32's config.py.
    While a treasure has a box, it can only be found after typing the box's code (a BoxProof).
    """

    __tablename__ = "treasure_boxes"
    id = db.Column(db.Integer, primary_key=True)
    treasure_id = db.Column(db.Integer, db.ForeignKey("treasures.id"), nullable=False, unique=True)
    secret = db.Column(db.String(64), nullable=False)  # hex
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)


class BoxProof(db.Model):
    """B: a player typed the right code at a box. Each code (counter) works for one player only."""

    __tablename__ = "box_proofs"
    __table_args__ = (db.UniqueConstraint("box_id", "user_id", name="one_proof_per_player"),
                      db.UniqueConstraint("box_id", "counter", name="one_player_per_code"))
    id = db.Column(db.Integer, primary_key=True)
    box_id = db.Column(db.Integer, db.ForeignKey("treasure_boxes.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    counter = db.Column(db.Integer, nullable=False)  # which 30-second code it was
    at = db.Column(db.DateTime, default=_utcnow, nullable=False)


class WandererCatch(db.Model):
    """B: a player caught the wandering treasure (wanderer.py). Once per player per Taiwan day."""

    __tablename__ = "wanderer_catches"
    __table_args__ = (db.UniqueConstraint("user_id", "day", name="one_catch_per_day"),)
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    day = db.Column(db.Date, nullable=False)
    at = db.Column(db.DateTime, default=_utcnow, nullable=False)


class TeamLock(db.Model):
    """B: a treasure that opens only when `need` players are at it together (team_lock.py)."""

    __tablename__ = "team_locks"
    id = db.Column(db.Integer, primary_key=True)
    treasure_id = db.Column(db.Integer, db.ForeignKey("treasures.id"), nullable=False, unique=True)
    need = db.Column(db.Integer, nullable=False)  # 2 or 3
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)


class TeamCheckin(db.Model):
    """B: a player tapped "I'm here" at a team treasure. Old ones are deleted."""

    __tablename__ = "team_checkins"
    id = db.Column(db.Integer, primary_key=True)
    lock_id = db.Column(db.Integer, db.ForeignKey("team_locks.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    at = db.Column(db.DateTime, default=_utcnow, nullable=False)


class TeamOpen(db.Model):
    """B: the team lock opened for this player (so they may find the treasure, and got the team bonus)."""

    __tablename__ = "team_opens"
    __table_args__ = (db.UniqueConstraint("lock_id", "user_id", name="one_open_per_player"),)
    id = db.Column(db.Integer, primary_key=True)
    lock_id = db.Column(db.Integer, db.ForeignKey("team_locks.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    at = db.Column(db.DateTime, default=_utcnow, nullable=False)


class Traveler(db.Model):
    """B: a traveling treasure that players carry from treasure to treasure (travelers.py).

    Where it is now is not stored here: it comes from its moves (the last one wins).
    """

    __tablename__ = "travelers"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(30), nullable=False)
    goal_treasure_id = db.Column(db.Integer, db.ForeignKey("treasures.id"), nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)


class TravelerMove(db.Model):
    """B: one move of a traveler: released or dropped at a treasure, or picked up by a player."""

    __tablename__ = "traveler_moves"
    id = db.Column(db.Integer, primary_key=True)
    traveler_id = db.Column(db.Integer, db.ForeignKey("travelers.id"), nullable=False, index=True)
    action = db.Column(db.String(10), nullable=False)  # travelers.RELEASE, PICK or DROP
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    treasure_id = db.Column(db.Integer, db.ForeignKey("treasures.id"), nullable=False)  # where (picked from, or left at)
    at = db.Column(db.DateTime, default=_utcnow, nullable=False)

"""Database tables for the treasure hunt. Owner: B.

Flask-SQLAlchemy turns each class below into a table in a SQLite file.
Every db.Column attribute becomes a column in that table.
"""

from datetime import datetime, timezone

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import validates

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
    """A player. More columns (password, weight, coins) come in later weeks."""

    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)

    # user.treasures gives every treasure this player uploaded
    treasures = db.relationship("Treasure", back_populates="creator")


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


def seed_demo_data():
    """Save the demo treasure if there are no treasures yet.

    Safe to call every time the app starts: it never adds duplicates.
    """
    first_treasure = db.session.execute(db.select(Treasure.id).limit(1)).first()
    if first_treasure is None:
        db.session.add(Treasure(**DEMO_TREASURE))
        db.session.commit()

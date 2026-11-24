"""Street crossings added by hand by an admin (owner: A, Feature 7 fallback).

OpenStreetMap doesn't know every crossing, and the free Overpass servers are sometimes
down. An admin can tap the admin map and add a crossing; it then warns players just like
the OpenStreetMap ones. Saved in its own table (manual_crossings).

The ids sent to the map are NEGATIVE (-1, -2, ...) so they never clash with
OpenStreetMap's ids, which are always positive.
"""

from datetime import datetime, timezone

from flask import current_app

from models import db

KINDS = ("street crossing", "zebra crossing", "crossing with traffic lights", "railway crossing")


class ManualCrossing(db.Model):
    __tablename__ = "manual_crossings"
    id = db.Column(db.Integer, primary_key=True)
    lat = db.Column(db.Float, nullable=False)
    lon = db.Column(db.Float, nullable=False)
    kind = db.Column(db.String(40), nullable=False, default="street crossing")
    added_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {"id": -self.id, "lat": self.lat, "lon": self.lon, "kind": self.kind, "manual": True}


def parse_kind(value):
    """One of KINDS; empty means a plain street crossing. Raises ValueError."""
    if value is None or value == "":
        return KINDS[0]
    if value not in KINDS:
        raise ValueError(f"kind must be one of: {', '.join(KINDS)}")
    return value


def all_manual():
    """Every hand-added crossing, as map dicts. None when the app has no database
    (some route tests run without one)."""
    if "sqlalchemy" not in current_app.extensions:
        return []
    rows = db.session.execute(db.select(ManualCrossing).order_by(ManualCrossing.id)).scalars().all()
    return [row.to_dict() for row in rows]

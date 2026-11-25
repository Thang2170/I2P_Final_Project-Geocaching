"""Download my data, and delete my band data (owner: B). Rules live in privacy.py.

- GET  /api/me/export           every row that points at you, as one JSON file
- POST /api/me/band-data/delete {"confirm": "DELETE"}   readings, paired bands, safety stops

The export follows the database's own links (foreign keys to users), so tables added later
are in it too, without anyone remembering to add them here.
"""

import json
from datetime import datetime, timezone

from flask import Blueprint, Response, jsonify, request
from sqlalchemy import delete, or_, select

from auth_api import current_user
from models import db
from privacy import BAND_TABLES, clean_row, confirm_problem, deleted_text, export_document, export_filename

privacy_api = Blueprint("privacy_api", __name__)


def _user_columns(table):
    """The columns of this table that point at a player."""
    return [c for c in table.columns if any(fk.column.table.name == "users" for fk in c.foreign_keys)]


def collect(user_id):
    """{table name: [rows as dicts]} for every row that points at this player (and their own row)."""
    tables = {}
    for table in db.metadata.sorted_tables:
        if table.name == "users":
            where = table.c.id == user_id
        else:
            columns = _user_columns(table)
            if not columns:
                continue
            where = or_(*(c == user_id for c in columns))
        rows = db.session.execute(select(table).where(where)).mappings().all()
        tables[table.name] = [clean_row(table.name, dict(r)) for r in rows]
    return tables


@privacy_api.route("/api/me/export")
def export_my_data():
    user = current_user()
    if user is None:
        return jsonify(error="Log in first"), 401
    now = datetime.now(timezone.utc)
    document = export_document(user.username, collect(user.id), now)
    return Response(json.dumps(document, ensure_ascii=False, indent=2), mimetype="application/json",
                    headers={"Content-Disposition": f'attachment; filename="{export_filename(user.username, now)}"',
                             "Cache-Control": "no-store"})


@privacy_api.route("/api/me/band-data/delete", methods=["POST"])
def delete_band_data():
    user = current_user()
    if user is None:
        return jsonify(error="Log in first"), 401
    problem = confirm_problem(request.get_json(silent=True))
    if problem:
        return jsonify(error=problem), 400
    tables = {t.name: t for t in db.metadata.sorted_tables}
    deleted = {}
    for name in BAND_TABLES:  # readings first: they point at the paired bands
        table = tables[name]
        result = db.session.execute(delete(table).where(table.c.user_id == user.id))
        deleted[name] = result.rowcount
    db.session.commit()
    return jsonify(deleted=deleted, message=deleted_text(deleted))

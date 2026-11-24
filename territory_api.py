"""Claim the campus: teams, hexagon visits and this week's map (owner: B). Rules: territory.py.

- GET  /territory              the page
- GET  /api/territory          this week's hexagons, the scoreboard and your team
- POST /api/territory/team     {"team": "gold" | "teal" | "coral"}
record_visit() is called by walk_proof_api.record_point() every time the map sends your position.
"""

from datetime import datetime, timezone

from flask import Blueprint, jsonify, render_template, request

from auth_api import current_user
from models import HexVisit, TeamChoice, db
from streaks import local_day, week_start
from territory import ORIGIN, TEAMS, hex_corners, hex_of, leader, owners, parse_team, scoreboard
from walk_proof import teleports

territory_api = Blueprint("territory_api", __name__)


def _now():
    return datetime.now(timezone.utc)


def team_of(user_id):
    choice = db.session.get(TeamChoice, user_id)
    return choice.team if choice else None


def record_visit(user_id, lat, lon, when, previous=None):
    """Colour the hexagon you're in for your team (once a day). The caller commits.

    previous: your last (when, lat, lon) point, if any. A teleport from it doesn't count,
    the same rule as "prove you walked" (walk_proof.py).
    """
    team = team_of(user_id)
    if team is None:
        return False
    if previous is not None and teleports([previous, (when, lat, lon)]):
        return False
    q, r = hex_of(lat, lon)
    day = local_day(when)
    exists = db.session.execute(db.select(HexVisit.id).where(
        HexVisit.user_id == user_id, HexVisit.day == day, HexVisit.q == q, HexVisit.r == r)).first()
    if exists:
        return False
    db.session.add(HexVisit(user_id=user_id, team=team, q=q, r=r, day=day, week_start=week_start(day)))
    return True


@territory_api.route("/territory")
def territory_page():
    return render_template("territory.html", origin=ORIGIN, teams=TEAMS)


@territory_api.route("/api/territory")
def this_week():
    me = current_user()
    if me is None:
        return jsonify(error="Log in first"), 401
    monday = week_start(local_day(_now()))
    visits = db.session.execute(db.select(HexVisit.q, HexVisit.r, HexVisit.team).where(
        HexVisit.week_start == monday)).all()
    owned = owners([tuple(v) for v in visits])
    counts = {}
    for q, r, _team in visits:
        counts[(q, r)] = counts.get((q, r), 0) + 1
    players = dict(db.session.execute(db.select(TeamChoice.team, db.func.count()).group_by(TeamChoice.team)).all())
    board = scoreboard(owned, players)
    mine = db.session.execute(db.select(db.func.count()).select_from(HexVisit).where(
        HexVisit.user_id == me.id, HexVisit.week_start == monday)).scalar_one()
    return jsonify(
        week_start=monday.isoformat(),
        my_team=team_of(me.id),
        my_visits=mine,
        teams=board,
        leader=leader(board),
        hexes=[{"q": q, "r": r, "team": team, "visits": counts[(q, r)],
                "colour": TEAMS[team][1] if team else None,
                "corners": hex_corners(q, r)} for (q, r), team in owned.items()],
    )


@territory_api.route("/api/territory/team", methods=["POST"])
def choose_team():
    me = current_user()
    if me is None:
        return jsonify(error="Log in first"), 401
    try:
        team = parse_team(request.get_json(silent=True))
    except ValueError as err:
        return jsonify(error=str(err)), 400
    choice = db.session.get(TeamChoice, me.id)
    if choice is None:
        db.session.add(TeamChoice(user_id=me.id, team=team))
    else:
        choice.team, choice.chosen_at = team, _now()
    db.session.commit()
    return jsonify(team=team, name=TEAMS[team][0])

"""The weekly health report page (owner: B). Rules live in weekly_report.py.

- GET  /report                       the page
- GET  /api/report[?week=YYYY-MM-DD]  the report for the week containing that day (default: this week)
- POST /api/report/share             post this week's summary to the Community (once a week)

It gathers what other parts already keep: daily steps and minutes (goals.daily_numbers, from
the band and hunts), heart-rate zones (band readings), hunts, trails, safety stops and the streak.
"""

from datetime import date, datetime, timedelta, timezone

from flask import Blueprint, jsonify, render_template, request
from sqlalchemy.exc import IntegrityError

from auth_api import current_user
from goal_api import _days
from habits import ring_target
from health import max_heart_rate
from models import GoalChoice, Journey, Post, ReportShare, SafetyAlert, TrailWalk, db
from streaks import local_day, week_start
from walk_api import age_of
from weekly_report import build_report, share_text
from zone_coach import zone_seconds

report_api = Blueprint("report_api", __name__)

OLDEST_WEEKS = 52  # look back at most a year


def _utc_bounds(monday):
    """The week Monday 00:00 - next Monday 00:00 Taiwan time, as naive UTC (how SQLite keeps times)."""
    start = datetime.combine(monday, datetime.min.time()) - timedelta(hours=8)
    return start, start + timedelta(days=7)


def report_for(user, day):
    today = local_day(datetime.now(timezone.utc))
    monday = week_start(day)
    days = _days(user.id, monday - timedelta(days=7))  # this week and last week
    choice = db.session.get(GoalChoice, user.id)
    goal, started = (choice.goal, choice.started_on) if choice else (None, today)
    ring = ring_target(goal, days, min(today, monday + timedelta(days=6)), started)

    start, end = _utc_bounds(monday)
    from health_api import HealthReading  # here, not at the top: health_api imports walk_api
    readings = db.session.execute(db.select(HealthReading.at, HealthReading.hr).where(
        HealthReading.user_id == user.id, HealthReading.hr.is_not(None),
        HealthReading.at >= start, HealthReading.at < end)).all()
    zones = zone_seconds([tuple(r) for r in readings], max_heart_rate(age_of(user.id))) if readings else []
    hunts = db.session.execute(db.select(Journey.distance_m, Journey.duration_s, Journey.calories).where(
        Journey.user_id == user.id, Journey.created_at >= start, Journey.created_at < end)).all()
    trails = db.session.execute(db.select(TrailWalk.distance_m, TrailWalk.duration_s, TrailWalk.calories).where(
        TrailWalk.user_id == user.id, TrailWalk.created_at >= start, TrailWalk.created_at < end)).all()
    stops = db.session.execute(db.select(db.func.count()).select_from(SafetyAlert).where(
        SafetyAlert.user_id == user.id, SafetyAlert.created_at >= start, SafetyAlert.created_at < end)).scalar()
    streak = None
    if monday <= today <= monday + timedelta(days=6):
        from habit_api import streak_info  # here, not at the top: habit_api imports feed_api
        streak = streak_info(user, today)["current"]
    report = build_report(monday, today, days, ring, zones, [tuple(h) for h in hunts], [tuple(t) for t in trails],
                          stops, streak)
    shared = db.session.execute(db.select(ReportShare.post_id).where(
        ReportShare.user_id == user.id, ReportShare.week_start == monday)).scalar()
    oldest = week_start(today) - timedelta(weeks=OLDEST_WEEKS)
    return report | {
        "shared": shared is not None,
        "previous": (monday - timedelta(days=7)).isoformat() if monday - timedelta(days=7) >= oldest else None,
        "next": (monday + timedelta(days=7)).isoformat() if monday + timedelta(days=7) <= today else None,
    }


@report_api.route("/report")
def report_page():
    return render_template("report.html")


@report_api.route("/api/report")
def get_report():
    user = current_user()
    if user is None:
        return jsonify(error="Log in first"), 401
    today = local_day(datetime.now(timezone.utc))
    try:
        day = date.fromisoformat(request.args["week"]) if "week" in request.args else today
    except ValueError:
        return jsonify(error="week must be a date like 2026-11-23"), 400
    if day > today or day < today - timedelta(weeks=OLDEST_WEEKS):
        return jsonify(error=f"Pick a week from the last {OLDEST_WEEKS} weeks"), 400
    return jsonify(report_for(user, day))


@report_api.route("/api/report/share", methods=["POST"])
def share_report():
    """Post this week's report to the Community. Only steps, walks and the streak: no heart data."""
    user = current_user()
    if user is None:
        return jsonify(error="Log in first"), 401
    from feed_api import _last, too_soon  # the Community's own anti-spam wait
    today = local_day(datetime.now(timezone.utc))
    report = report_for(user, today)
    if report["shared"]:
        return jsonify(error="You already shared this week's report."), 400
    if not report["totals"]["steps"] and not report["totals"]["hunts"] + report["totals"]["trails"]:
        return jsonify(error="Nothing to share yet this week: go for a walk first!"), 400
    wait = too_soon("post", _last(Post, user.id, Post.journey_id.is_(None)))
    if wait:
        return wait
    post = Post(user_id=user.id, text=share_text(report))
    db.session.add(post)
    db.session.flush()
    db.session.add(ReportShare(post_id=post.id, user_id=user.id, week_start=week_start(today)))
    try:
        db.session.commit()
    except IntegrityError:  # a double tap
        db.session.rollback()
        return jsonify(error="You already shared this week's report."), 400
    return jsonify(post_id=post.id, text=post.text), 201

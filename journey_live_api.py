"""One live update for a journey or a timed trail (owner: B).

The map used to ask four addresses on four timers while you walk (steps and calories, the
heart-rate zone, the safety check, the try-hard pace). Now it asks this one, so a phone sends
far fewer requests and the journey code on the map is simpler:

    GET /api/journey/live?distance_m=850&duration_s=600

Answers {"stats", "zone", "safety", "mode"}. Each part is worked out by the same Python as its
own address (energy.py via walk_api, zone_api, safety_api, modes), so the answers are the same.
Logged out, only "stats" is filled in (the others need your band and settings).
"""

from flask import Blueprint, jsonify, request

from auth_api import current_user
from mode_api import mode_of
from modes import mode_line
from safety_api import safety_report
from walk_api import _saved_weight, energy_for
from walk_input import DEFAULT_WEIGHT_KG, parse_distance_m, parse_duration_s
from zone_api import zone_report

journey_live_api = Blueprint("journey_live_api", __name__)


@journey_live_api.route("/api/journey/live")
def journey_live():
    try:
        distance_m = parse_distance_m(request.args.get("distance_m"))
        duration_s = parse_duration_s(request.args.get("duration_s"))
    except ValueError as err:
        return jsonify(error=str(err)), 400
    user = current_user()
    energy = energy_for(user, distance_m, _saved_weight(user) or DEFAULT_WEIGHT_KG, duration_s)
    stats = {"steps": energy["steps"], "calories": energy["calories"], "source": energy["source"],
             "source_text": energy["source_text"]}
    if user is None:
        return jsonify(stats=stats, zone=None, safety=None, mode=None)
    return jsonify(stats=stats, zone=zone_report(user, duration_s), safety=safety_report(user),
                   mode=mode_line(mode_of(user), distance_m, duration_s))

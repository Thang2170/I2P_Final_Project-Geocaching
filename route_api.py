"""The /api/route endpoint (owner: A).

It lives in its own Blueprint so A does not have to edit much of B's app.py.
app.py only needs two lines:

    from route_api import route_api
    app.register_blueprint(route_api)
"""

from flask import Blueprint, jsonify, request

from routing import get_route, parse_points

route_api = Blueprint("route_api", __name__)


@route_api.route("/api/route")
def api_route():
    """GET /api/route?points=lat,lon;lat,lon[;lat,lon...]  (2 to 10 points)."""
    try:
        points = parse_points(request.args.get("points", ""))
    except ValueError as err:
        return jsonify(error=str(err)), 400
    return jsonify(get_route(points))
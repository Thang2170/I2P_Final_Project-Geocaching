"""The /api/route and /api/random-route endpoints (owner: A).

They live in their own Blueprint so A does not have to edit much of B's app.py.
app.py only needs two lines:

    from route_api import route_api
    app.register_blueprint(route_api)
"""

from flask import Blueprint, jsonify, request

from routing import check_point, drop_reached_via, get_random_route, get_route, parse_points

route_api = Blueprint("route_api", __name__)


@route_api.route("/api/route")
def api_route():
    """GET /api/route?points=lat,lon;lat,lon[;lat,lon...]  (2 to 10 points).

    The first point is where the walker is. A middle stop they already reached
    is dropped, and "via_reached" tells the map to stop sending it.
    """
    try:
        points = parse_points(request.args.get("points", ""))
    except ValueError as err:
        return jsonify(error=str(err)), 400
    kept = drop_reached_via(points)
    route = get_route(kept)
    if len(kept) < len(points):
        route["via_reached"] = True
    return jsonify(route)


@route_api.route("/api/random-route")
def api_random_route():
    """GET /api/random-route?points=lat,lon;lat,lon[&current=lat,lon]

    points: exactly 2, you then the treasure. current (optional): the "via" of the
    route the map shows now, so the new route is a different one.
    The answer is a normal route plus "via": [lat, lon].
    """
    try:
        points = parse_points(request.args.get("points", ""))
        if len(points) != 2:
            raise ValueError("Need exactly 2 points: where you are, then the treasure")
        current = request.args.get("current")
        current_via = check_point(current.split(",")) if current else None
        route = get_random_route(points[0], points[1], current_via=current_via)
    except ValueError as err:
        return jsonify(error=str(err)), 400
    return jsonify(route)

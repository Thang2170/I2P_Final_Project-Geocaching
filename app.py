from flask import Flask, jsonify, render_template, request

from location import haversine_m

app = Flask(__name__)

# Fake treasure for now. B will move this into the database later.
TREASURE = {"name": "National Tsing Hua University", "lat": 24.795324, "lon": 120.994796}


@app.route("/")
def home():
    return render_template("map.html", treasure=TREASURE)


@app.route("/api/distance")
def distance():
    try:
        lat = float(request.args["lat"])
        lon = float(request.args["lon"])
    except (KeyError, ValueError):
        return jsonify(error="Need numeric lat and lon"), 400

    meters = haversine_m(lat, lon, TREASURE["lat"], TREASURE["lon"])
    return jsonify(treasure=TREASURE["name"], meters=round(meters, 1))


if __name__ == "__main__":
    app.run(debug=True)
from math import asin, cos, radians, sin, sqrt

EARTH_RADIUS_M = 6_371_000  


def haversine_m(lat1, lon1, lat2, lon2):
    """Return the distance in meters between two GPS points (inputs in degrees)."""
    # sin() and cos() want radians, but GPS gives degrees
    phi1, phi2 = radians(lat1), radians(lat2)
    d_phi = radians(lat2 - lat1)
    d_lambda = radians(lon2 - lon1)

    a = sin(d_phi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(d_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_M * asin(sqrt(a))
def is_near(lat1, lon1, lat2, lon2, threshold_m=20):
    """Return True if the two GPS points are within threshold_m meters of each other."""
    return haversine_m(lat1, lon1, lat2, lon2) <= threshold_m
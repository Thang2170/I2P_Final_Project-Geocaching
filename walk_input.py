"""Check the numbers sent to the steps-and-calories endpoint. Owner: B.

Plain Python with no Flask and no database, so it is easy to test.
"""

from treasure_input import parse_number

DEFAULT_WEIGHT_KG = 65       # used when we know nothing better about the player
MIN_WEIGHT_KG = 20
MAX_WEIGHT_KG = 300
MAX_DISTANCE_M = 200_000     # 200 km: more than any walk in this app


def parse_distance_m(value):
    """Return a walking distance in meters as a float, or raise ValueError."""
    return parse_number(value, "distance_m", 0, MAX_DISTANCE_M)


def parse_weight_kg(value):
    """Return a body weight in kilograms as a float, or raise ValueError."""
    return parse_number(value, "weight_kg", MIN_WEIGHT_KG, MAX_WEIGHT_KG)

"""Weather-aware route choices (owner: B; C's idea).

The weather comes from Open-Meteo (free, no key needed). From it Python picks how to walk:
- rain or a thunderstorm on the way: the SHORTEST route, and a warning
- heat or strong sun: a GREENER route (more trees, so more shade), and a water reminder
- nice weather: a slightly greener, nicer route
- cold or wind: the normal route, with a tip

Everything except fetch_weather() is plain Python with no network, so it is easy to test.
Tests never call Open-Meteo: they patch weather.requests.get.
"""

import requests

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
TIMEOUT_S = 4

RAIN_MM = 0.2            # rain falling now (mm in the last hour)
RAIN_CHANCE = 60         # % chance of rain in the next hour
HOT_FEELS_C = 32         # "feels like" temperature
STRONG_UV = 8
COLD_FEELS_C = 12        # cold for Hsinchu
WINDY_KMH = 40

# WMO weather codes (Open-Meteo uses them)
RAIN_CODES = set(range(51, 68)) | set(range(80, 83))
THUNDER_CODES = {95, 96, 99}
CODE_WORDS = {0: "clear sky", 1: "mainly clear", 2: "partly cloudy", 3: "cloudy", 45: "fog", 48: "fog",
              51: "light drizzle", 53: "drizzle", 55: "heavy drizzle", 61: "light rain", 63: "rain",
              65: "heavy rain", 80: "light showers", 81: "showers", 82: "heavy showers",
              95: "thunderstorm", 96: "thunderstorm with hail", 99: "thunderstorm with hail"}

# What the route service is asked for (OpenRouteService foot-walking options)
SHORTEST = {"preference": "shortest"}
GREEN = {"options": {"profile_params": {"weightings": {"green": 1.0}}}}
A_BIT_GREEN = {"options": {"profile_params": {"weightings": {"green": 0.5}}}}


class WeatherError(Exception):
    """Open-Meteo could not tell us the weather."""


def fetch_weather(lat, lon):
    """The weather now at (lat, lon), from Open-Meteo. Raises WeatherError."""
    params = {
        "latitude": round(lat, 3), "longitude": round(lon, 3), "timezone": "auto", "forecast_hours": 1,
        "current": "temperature_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m,uv_index,is_day",
        "hourly": "precipitation_probability",
    }
    try:
        response = requests.get(OPEN_METEO_URL, params=params, timeout=TIMEOUT_S)
    except requests.RequestException as err:
        raise WeatherError(f"Could not reach the weather service ({err.__class__.__name__})") from err
    if response.status_code != 200:
        raise WeatherError(f"Weather service error {response.status_code}")
    try:
        return parse_weather(response.json())
    except (KeyError, TypeError, ValueError) as err:
        raise WeatherError("The weather service sent an unexpected answer") from err


def parse_weather(data):
    """Open-Meteo's answer -> a small, clean dict. Raises KeyError/TypeError/ValueError if it is odd."""
    now = data["current"]
    chances = (data.get("hourly") or {}).get("precipitation_probability") or []
    code = int(now["weather_code"])
    return {
        "temp_c": round(float(now["temperature_2m"]), 1),
        "feels_c": round(float(now["apparent_temperature"]), 1),
        "rain_mm": round(float(now.get("precipitation") or 0), 1),
        "rain_chance": int(chances[0]) if chances and chances[0] is not None else 0,
        "code": code,
        "words": CODE_WORDS.get(code, "mixed weather"),
        "wind_kmh": round(float(now.get("wind_speed_10m") or 0)),
        "uv": round(float(now.get("uv_index") or 0), 1),
        "is_day": bool(now.get("is_day", 1)),
    }


def route_choice(w):
    """How to walk in this weather.

    Returns {"kind", "headline", "tip", "route_options"}; route_options is sent to the route
    service (empty = the normal route). w is parse_weather()'s dict, or None if unknown.
    """
    if w is None:
        return {"kind": "unknown", "headline": "", "tip": "", "route_options": {}}
    if w["code"] in THUNDER_CODES:
        return {"kind": "storm", "headline": f"⛈ Thunderstorm ({w['temp_c']:.0f}°C): shortest route",
                "tip": "Lightning is dangerous outside. Wait indoors until it passes, then take the short way.",
                "route_options": SHORTEST}
    if w["rain_mm"] >= RAIN_MM or w["code"] in RAIN_CODES or w["rain_chance"] >= RAIN_CHANCE:
        raining = w["rain_mm"] >= RAIN_MM or w["code"] in RAIN_CODES
        what = "Rain" if raining else "Rain likely ({}%)".format(w["rain_chance"])
        return {"kind": "rain",
                "headline": f"🌧 {what}: shortest route",
                "tip": "Take an umbrella and watch for slippery steps and tiles.",
                "route_options": SHORTEST}
    if w["feels_c"] >= HOT_FEELS_C or (w["is_day"] and w["uv"] >= STRONG_UV):
        return {"kind": "heat", "headline": f"☀ Hot (feels {w['feels_c']:.0f}°C, UV {w['uv']:.0f}): shadier, greener route",
                "tip": "Bring water and rest in the shade if you feel dizzy.",
                "route_options": GREEN}
    if w["feels_c"] <= COLD_FEELS_C:
        return {"kind": "cold", "headline": f"🧣 Cold (feels {w['feels_c']:.0f}°C)",
                "tip": "Wear a warm layer. Walking warms you up after a few minutes.", "route_options": {}}
    if w["wind_kmh"] >= WINDY_KMH:
        return {"kind": "wind", "headline": f"💨 Windy ({w['wind_kmh']} km/h)",
                "tip": "Hsinchu wind is strong: hold on to your phone and hat.", "route_options": {}}
    return {"kind": "nice", "headline": f"🌤 {w['words'].capitalize()}, {w['temp_c']:.0f}°C: a greener route",
            "tip": "Nice weather for a walk.", "route_options": A_BIT_GREEN}


def area_key(lat, lon):
    """Weather is the same for about 1 km around: one cache entry per 0.01 degree square."""
    return round(lat, 2), round(lon, 2)

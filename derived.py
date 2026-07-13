"""Derived meteorological and air-quality metrics.

Pure functions with no I/O — computed from the raw sensor columns and shared
by the Flask app (for display) and the alert engine. Every function tolerates
None inputs and returns None when it can't compute a meaningful value, so
callers can pass partial sensor state straight through.
"""
import math

CARDINALS = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
             "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]


def cardinal_direction(degrees):
    """Compass degrees -> 16-point cardinal string (e.g. 'NNE')."""
    if degrees is None:
        return None
    return CARDINALS[round((int(degrees) % 360) / 22.5) % 16]


def dew_point(temp_c, humidity_pct):
    """Dew point in °C via the Magnus-Tetens approximation."""
    if temp_c is None or humidity_pct is None or humidity_pct <= 0:
        return None
    a, b = 17.27, 237.7
    gamma = (a * temp_c) / (b + temp_c) + math.log(humidity_pct / 100.0)
    return round((b * gamma) / (a - gamma), 1)


def heat_index(temp_c, humidity_pct):
    """Apparent temperature ('feels like' when hot) in °C.

    Uses the NOAA Rothfusz regression (valid above ~27°C / 80% RH-relevant
    range). Below 27°C the heat index isn't meaningful, so we return the air
    temperature unchanged.
    """
    if temp_c is None or humidity_pct is None:
        return None
    if temp_c < 27:
        return round(temp_c, 1)
    t = temp_c * 9 / 5 + 32  # NOAA regression is defined in °F
    r = humidity_pct
    hi = (-42.379 + 2.04901523 * t + 10.14333127 * r
          - 0.22475541 * t * r - 6.83783e-3 * t * t
          - 5.481717e-2 * r * r + 1.22874e-3 * t * t * r
          + 8.5282e-4 * t * r * r - 1.99e-6 * t * t * r * r)
    return round((hi - 32) * 5 / 9, 1)


def wind_chill(temp_c, wind_speed_ms):
    """Wind chill in °C (only meaningful when cold and windy)."""
    if temp_c is None or wind_speed_ms is None:
        return None
    if temp_c > 10 or wind_speed_ms < 1.34:  # ~4.8 km/h
        return round(temp_c, 1) if temp_c is not None else None
    v = (wind_speed_ms * 3.6) ** 0.16  # wind in km/h
    wc = 13.12 + 0.6215 * temp_c - 11.37 * v + 0.3965 * temp_c * v
    return round(wc, 1)


def feels_like(temp_c, humidity_pct, wind_speed_ms):
    """Best single 'feels like' number: heat index when warm, wind chill when
    cold, otherwise the air temperature."""
    if temp_c is None:
        return None
    if temp_c >= 27:
        return heat_index(temp_c, humidity_pct)
    if temp_c <= 10:
        return wind_chill(temp_c, wind_speed_ms)
    return round(temp_c, 1)


# --- US EPA Air Quality Index -------------------------------------------------
# (Cp_low, Cp_high, I_low, I_high) breakpoints, 2024 PM2.5 revision.
_PM25_BREAKPOINTS = [
    (0.0, 9.0, 0, 50), (9.1, 35.4, 51, 100), (35.5, 55.4, 101, 150),
    (55.5, 125.4, 151, 200), (125.5, 225.4, 201, 300), (225.5, 500.4, 301, 500),
]
_PM10_BREAKPOINTS = [
    (0, 54, 0, 50), (55, 154, 51, 100), (155, 254, 101, 150),
    (255, 354, 151, 200), (355, 424, 201, 300), (425, 604, 301, 500),
]
AQI_CATEGORIES = [
    (50, "Good", "#009966"),
    (100, "Moderate", "#f2c500"),
    (150, "Unhealthy for Sensitive Groups", "#ff7e00"),
    (200, "Unhealthy", "#cc0033"),
    (300, "Very Unhealthy", "#8f3f97"),
    (500, "Hazardous", "#7e0023"),
]


def _aqi_from_breakpoints(conc, breakpoints):
    if conc is None:
        return None
    conc = round(conc, 1)
    for cp_lo, cp_hi, i_lo, i_hi in breakpoints:
        if cp_lo <= conc <= cp_hi:
            return round((i_hi - i_lo) / (cp_hi - cp_lo) * (conc - cp_lo) + i_lo)
    if conc > breakpoints[-1][1]:
        return breakpoints[-1][3]  # cap at 500
    return None


def aqi_category(aqi):
    """AQI number -> (label, hex color)."""
    if aqi is None:
        return (None, None)
    for ceiling, label, color in AQI_CATEGORIES:
        if aqi <= ceiling:
            return (label, color)
    return (AQI_CATEGORIES[-1][1], AQI_CATEGORIES[-1][2])


def air_quality(pm2_5, pm10_0):
    """Overall AQI as the worst of the PM2.5 and PM10 sub-indices, with the
    dominant pollutant and category. Returns a dict (fields None if unknown)."""
    aqi_pm25 = _aqi_from_breakpoints(pm2_5, _PM25_BREAKPOINTS)
    aqi_pm10 = _aqi_from_breakpoints(pm10_0, _PM10_BREAKPOINTS)
    candidates = [(aqi_pm25, "PM2.5"), (aqi_pm10, "PM10")]
    candidates = [c for c in candidates if c[0] is not None]
    if not candidates:
        return {"aqi": None, "dominant": None, "category": None, "color": None}
    aqi, dominant = max(candidates, key=lambda c: c[0])
    label, color = aqi_category(aqi)
    return {"aqi": aqi, "dominant": dominant, "category": label, "color": color}


def uv_category(uv):
    """UV index -> (label, hex color) per WHO bands."""
    if uv is None:
        return (None, None)
    if uv < 3:
        return ("Low", "#009966")
    if uv < 6:
        return ("Moderate", "#f2c500")
    if uv < 8:
        return ("High", "#ff7e00")
    if uv < 11:
        return ("Very High", "#cc0033")
    return ("Extreme", "#8f3f97")


# Beaufort scale: (max wind speed m/s inclusive, force, description).
_BEAUFORT = [
    (0.3, 0, "Calm"), (1.5, 1, "Light air"), (3.3, 2, "Light breeze"),
    (5.5, 3, "Gentle breeze"), (7.9, 4, "Moderate breeze"),
    (10.7, 5, "Fresh breeze"), (13.8, 6, "Strong breeze"),
    (17.1, 7, "Near gale"), (20.7, 8, "Gale"), (24.4, 9, "Strong gale"),
    (28.4, 10, "Storm"), (32.6, 11, "Violent storm"),
]


def beaufort(wind_speed_ms):
    """Wind speed -> (force number, description)."""
    if wind_speed_ms is None:
        return (None, None)
    for ceiling, force, desc in _BEAUFORT:
        if wind_speed_ms <= ceiling:
            return (force, desc)
    return (12, "Hurricane force")


def pressure_trend(current, past):
    """Compare current pressure to a value ~3h ago -> (label, delta hPa).

    Standard marine thresholds: a change of ≥1 hPa over 3h is notable.
    """
    if current is None or past is None:
        return (None, None)
    delta = round(current - past, 1)
    if delta >= 1.0:
        return ("rising", delta)
    if delta <= -1.0:
        return ("falling", delta)
    return ("steady", delta)


def enrich(data):
    """Add all derived fields to a dict of raw sensor readings, in place.

    `data` is expected to hold the standard column keys (temperature,
    humidity, ...). Missing keys are treated as None. Returns the same dict.
    """
    temp = data.get("temperature")
    hum = data.get("humidity")
    wind = data.get("wind_speed")

    data["wind_direction_cardinal"] = cardinal_direction(data.get("wind_direction"))
    data["dew_point"] = dew_point(temp, hum)
    data["heat_index"] = heat_index(temp, hum)
    data["feels_like"] = feels_like(temp, hum, wind)

    aq = air_quality(data.get("pm2_5"), data.get("pm10_0"))
    data["aqi"] = aq["aqi"]
    data["aqi_dominant"] = aq["dominant"]
    data["aqi_category"] = aq["category"]
    data["aqi_color"] = aq["color"]

    uv_label, uv_color = uv_category(data.get("uv_index"))
    data["uv_category"] = uv_label
    data["uv_color"] = uv_color

    force, desc = beaufort(wind)
    data["beaufort_force"] = force
    data["beaufort_desc"] = desc
    return data

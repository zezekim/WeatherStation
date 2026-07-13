"""Shared configuration.

Reads settings from a .env file next to this script (stdlib only — no
python-dotenv dependency needed on the Pi). Real environment variables take
precedence over .env values.

Importing this module never fails, so read-only consumers (the Flask app,
the rollup job) can use the station metadata and thresholds without needing
MQTT credentials. Publishers/subscribers call require_mqtt() to assert that
credentials are present before connecting.
"""
import os
import sys

_ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")

if os.path.exists(_ENV_PATH):
    with open(_ENV_PATH) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())


def _get(name, default=None):
    return os.environ.get(name, default)


def _get_float(name, default):
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return float(default)


# --- MQTT ---
MQTT_BROKER = _get("MQTT_BROKER", "localhost")
MQTT_PORT = int(_get("MQTT_PORT", "1883"))
MQTT_USER = _get("MQTT_USER")
MQTT_PASS = _get("MQTT_PASS")

# --- Station metadata (used by the dashboard map/forecast + title) ---
STATION_NAME = _get("STATION_NAME", "JAGASA Environmental Station")
STATION_LAT = _get_float("STATION_LAT", 14.59)
STATION_LON = _get_float("STATION_LON", 121.16)

# --- Data retention (rollup.py) ---
# Raw 15-second rows older than this many days are compacted to hourly averages.
RETENTION_DAYS = int(_get("RETENTION_DAYS", "30"))

# --- Alert thresholds ---
# Each entry: metric -> {level: (comparator, value)}. Comparators are ">" / "<".
# Levels are ordered least-to-most severe; the most severe breached level wins.
# Tuned for a hot, humid tropical site; override any of these in .env.
ALERT_THRESHOLDS = {
    "heat_index": [
        ("warning", ">", _get_float("ALERT_HEAT_INDEX_WARN", 33)),
        ("danger", ">", _get_float("ALERT_HEAT_INDEX_DANGER", 41)),
    ],
    "pm2_5": [
        ("warning", ">", _get_float("ALERT_PM25_WARN", 35.4)),
        ("danger", ">", _get_float("ALERT_PM25_DANGER", 55.4)),
    ],
    "pm10_0": [
        ("warning", ">", _get_float("ALERT_PM10_WARN", 154)),
        ("danger", ">", _get_float("ALERT_PM10_DANGER", 254)),
    ],
    "uv_index": [
        ("warning", ">", _get_float("ALERT_UV_WARN", 8)),
        ("danger", ">", _get_float("ALERT_UV_DANGER", 11)),
    ],
    "wind_speed": [
        ("warning", ">", _get_float("ALERT_WIND_WARN", 10)),
        ("danger", ">", _get_float("ALERT_WIND_DANGER", 17)),
    ],
    "pressure": [
        ("warning", "<", _get_float("ALERT_PRESSURE_WARN", 1000)),
        ("danger", "<", _get_float("ALERT_PRESSURE_DANGER", 990)),
    ],
}


def require_mqtt():
    """Assert MQTT credentials are configured; exit with a clear message if not.

    Called by the publishers and logger at startup so a missing .env fails
    loudly instead of silently connecting anonymously.
    """
    if not MQTT_USER or not MQTT_PASS:
        sys.exit(
            "Missing MQTT credentials: set MQTT_USER and MQTT_PASS in "
            f"{_ENV_PATH} (see .env.example) or as environment variables."
        )
    return MQTT_BROKER, MQTT_PORT, MQTT_USER, MQTT_PASS

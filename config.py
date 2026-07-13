"""Shared configuration. Reads MQTT settings from a .env file next to this
script (stdlib only — no python-dotenv dependency needed on the Pi).
Real environment variables take precedence over .env values."""
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

MQTT_BROKER = os.environ.get("MQTT_BROKER", "localhost")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
MQTT_USER = os.environ.get("MQTT_USER")
MQTT_PASS = os.environ.get("MQTT_PASS")

if not MQTT_USER or not MQTT_PASS:
    sys.exit("Missing MQTT credentials: set MQTT_USER and MQTT_PASS in "
             f"{_ENV_PATH} (see .env.example) or as environment variables.")

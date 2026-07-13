# WeatherStation

A Raspberry Pi–based environmental monitoring station (JAGASA Environmental Station) that collects weather and air-quality data from a mix of Modbus, UART, and ESPHome sensors, aggregates it over MQTT, logs it to SQLite, and serves a live web dashboard with 72-hour history charts.

## How it works

```
┌─────────────────┐     ┌──────────────────┐
│ Modbus sensors   │     │ ESPHome nodes    │
│ (wind speed/dir) │     │ (temp, humidity, │
│                  │     │  pressure, UV,   │
│ PM2.5 sensor     │     │  lux, VOC, PM)   │
│ (UART)           │     │                  │
└───────┬─────────┘     └────────┬─────────┘
        │  publish                │  publish
        ▼                         ▼
              MQTT broker (Mosquitto)
                        │  subscribe (#)
                        ▼
              mqtt_logger.py ──► weather_data.db (SQLite)
                                          │
                                          ▼
                             w.py (Flask) ──► Web dashboard
```

- **`modbus_hub.py`** — Polls RS-485 Modbus wind speed and wind direction sensors every 2 seconds and publishes readings to MQTT under the `pi_hub/` topic prefix. Automatically reconnects on serial/Modbus errors.
- **`pm25_hub.py`** — Reads a PMS-family particulate sensor over UART (PM1.0 / PM2.5 / PM10) every 5 seconds and publishes to MQTT.
- **`mqtt_logger.py`** — Subscribes to all MQTT topics, translates sensor topic names (including ESPHome-sanitized names) into a standard schema, keeps the latest value of every metric in memory, and snapshots the full state into SQLite every 15 seconds.
- **`w.py`** — Flask web app. Serves the dashboard (`templates/index.html`) and two JSON endpoints:
  - `GET /data` — latest reading, enriched with a cardinal wind direction (N/NNE/…) and a simple pressure/humidity/wind-based weather outlook.
  - `GET /history/<data_type>` — the last 72 hours of a single metric for charting.

## Metrics collected

| Category | Metrics |
|---|---|
| Weather | temperature, humidity, pressure, wind speed, wind direction |
| Light | ambient light (lux), UV index |
| Air quality | PM1.0, PM2.5, PM10, VOC index |

## Setup

Requires Python 3.11+, an MQTT broker (e.g. Mosquitto), and the sensor hardware above. Serial devices are expected at stable udev-mapped paths (`/dev/wind_speed`, `/dev/wind_direction`, `/dev/pm25_sensor`).

```bash
python3 -m venv venv
source venv/bin/activate
pip install flask paho-mqtt pymodbus pyserial adafruit-circuitpython-pm25 gunicorn

# Create the database (WARNING: drops any existing weather_readings table)
python init_db.py
```

Configure the MQTT broker address and credentials at the top of `modbus_hub.py`, `pm25_hub.py`, and `mqtt_logger.py`.

## Running

Each component runs as its own long-lived process (typically as systemd services on the Pi):

```bash
python modbus_hub.py     # wind sensors → MQTT
python pm25_hub.py       # particulate sensor → MQTT
python mqtt_logger.py    # MQTT → SQLite
python w.py              # or: gunicorn w:app — web dashboard
```

`check_db.py` prints the 20 most recent database rows for a quick health check.

## Database

Single SQLite table `weather_readings` (see `schema.sql`): one row per 15-second snapshot with a Unix `timestamp` and one nullable column per metric, indexed on `timestamp`.

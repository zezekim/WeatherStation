# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

A Raspberry Pi weather/air-quality station. Sensor hub scripts publish readings to an MQTT broker; a logger persists them to SQLite; a Flask app serves a live dashboard. There is no package manager manifest or test suite — this is a small set of standalone scripts sharing one database.

## Architecture and data flow

Sensors → MQTT → SQLite → Flask, with each stage a separate long-running process:

1. **Publishers** (run on the Pi, one process each):
   - `modbus_hub.py` — RS-485 Modbus wind speed/direction sensors, polled every 2 s, published to `pi_hub/<sensor>`.
   - `pm25_hub.py` — PMS particulate sensor over UART, published every 5 s.
   - External ESPHome nodes publish temperature, humidity, pressure, UV, lux, VOC, and PM topics directly.
2. **`mqtt_logger.py`** — subscribes to `#`, maps incoming topic names to standard column names via `TOPIC_MAP`, accumulates the latest value per metric in `current_state` (guarded by a `Lock`), and inserts a full-state snapshot row every 15 s. State is deliberately never cleared between snapshots — each row carries the last-known value of every metric.
3. **`w.py`** — Flask app reading `weather_data.db`. `/data` returns the newest row plus derived fields (cardinal wind direction, weather outlook); `/history/<type>` returns 72 h of one metric, validated against a whitelist before being interpolated into the SQL query.

## Key conventions

- **Topic mapping**: ESPHome sanitizes sensor names (e.g. `particulate_matter_2_5__m`). Any new sensor must be added to `TOPIC_MAP` in `mqtt_logger.py`; the key is the second-to-last topic segment for `/state` topics, otherwise the last segment.
- **Schema changes**: adding a metric requires touching `schema.sql`, the INSERT statement and defaults list in `mqtt_logger.py`, and the `valid_types` whitelist in `w.py`. `init_db.py` **drops and recreates** the table — never run it against a database with data worth keeping.
- **Timestamps** are Unix epoch seconds (integers) throughout.
- **Config**: MQTT broker/credentials live in `.env`, loaded by `config.py` (stdlib parser, no python-dotenv — the Pi venv can't be assumed to have it). `.env` is gitignored; `.env.example` documents the keys. Everything else (serial ports, intervals, topic prefix) is hardcoded at the top of each script. Serial devices use stable udev aliases like `/dev/wind_speed`.
- `backup/` contains one-off hardware test scripts and older iterations — reference only, not part of the running system, and gitignored because some still contain old credentials/API keys.
- `weather_data.db` (~100 MB) and `venv/` must never be committed.

## Running / checking

```bash
source venv/bin/activate
python w.py                 # dashboard on Flask dev server
python check_db.py          # print 20 most recent DB rows
```

The hub and logger scripts require the physical sensors and MQTT broker, so they can't be meaningfully run on a dev machine — verify changes to them by review, and test DB/web changes against the local `weather_data.db`.

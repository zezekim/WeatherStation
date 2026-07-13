# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

A Raspberry Pi weather/air-quality station. Sensor hub scripts publish readings to an MQTT broker; a logger persists them to SQLite; a Flask app serves a live dashboard. There is no package manager manifest or test suite — this is a small set of standalone scripts sharing one database.

## Module map

- `config.py` — loads `.env` (stdlib parser); exposes MQTT + station + threshold settings. Importing never fails; publishers/logger call `require_mqtt()` to assert credentials. Read-only consumers (`w.py`, `rollup.py`) import it freely.
- `derived.py` — pure functions for derived metrics (dew point, heat index, feels-like, US EPA AQI, UV band, Beaufort, cardinal, pressure trend). `enrich(dict)` adds them all in place. Shared by `w.py` and the logger.
- `alerts.py` — `evaluate_alerts(reading)` → active alerts from `config.ALERT_THRESHOLDS`. Pure; used by `w.py` (dashboard) and the logger (MQTT publish).
- `w.py` — Flask app + API: `/data`, `/history/<metric>`, `/summary`.
- `rollup.py` — retention job (see below).
- `systemd/*.service` + `deploy.sh` — deployment. The station runs as four systemd services (`modbus_hub`, `pm25_hub`, `mqtt_logger`, `weather`) as user `rs` from `/home/rs/weather`. `deploy.sh` (run as `rs`, uses sudo internally) stops the old services, does a `git reset --hard` that preserves the gitignored DB/`.env`/`venv`, syncs deps, installs the units, and restarts. Adding/renaming a service means updating both `systemd/` and the `SERVICES` array in `deploy.sh`. Note `pm25_hub.service` still declares `Requires=pigpiod.service` from an earlier pigpio-based implementation, though `pm25_hub.py` now uses pyserial.

## Architecture and data flow

Sensors → MQTT → SQLite → Flask, with each stage a separate long-running process:

1. **Publishers** (run on the Pi, one process each):
   - `modbus_hub.py` — RS-485 Modbus wind speed/direction sensors, polled every 2 s, published to `pi_hub/<sensor>`.
   - `pm25_hub.py` — PMS particulate sensor over UART, published every 5 s.
   - External ESPHome nodes publish temperature, humidity, pressure, UV, lux, VOC, and PM topics directly.
2. **`mqtt_logger.py`** — subscribes to `#`, maps incoming topic names to standard column names via `TOPIC_MAP` (module-level, not rebuilt per message), accumulates the latest value per metric in `current_state` (guarded by a `Lock`), and inserts a full-state snapshot row every 15 s. State is deliberately never cleared between snapshots — each row carries the last-known value of every metric. Each snapshot also evaluates alerts and publishes level *changes* to `pi_hub/alerts/<metric>` (retained), tracked in `last_alert_levels` so it doesn't spam.
3. **`w.py`** — Flask app reading `weather_data.db`.
   - `/data` returns the newest row, all `derived.enrich` fields, a 3 h pressure trend, `age_seconds`/`is_stale` (reading older than `STALE_AFTER`), the weather outlook, and active alerts.
   - `/history/<metric>?hours=&points=` downsamples with `GROUP BY CAST(timestamp AS INTEGER) / bucket` — note the CAST: `timestamp` is REAL, so dividing without casting produces unique float keys and defeats bucketing. Returns bucketed avg plus a min/max band. `hours`/`points` are clamped.
   - `/summary` returns per-metric min/max/avg since local midnight.

**Data-retention (`rollup.py`)**: compacts raw rows older than `RETENTION_DAYS` into one hourly-average row per hour. Idempotent (only hours with `COUNT(*) > 1` are compacted; already-rolled singleton hours are skipped) and transactional (temp table → delete only the hours being compacted → insert). Run nightly from cron; supports `--dry-run`, `--vacuum`, `--days`, `--db`. Test it against a **copy**, never the live DB.

## Key conventions

- **Topic mapping**: ESPHome sanitizes sensor names (e.g. `particulate_matter_2_5__m`). Any new sensor must be added to `TOPIC_MAP` in `mqtt_logger.py`; the key is the second-to-last topic segment for `/state` topics, otherwise the last segment.
- **Schema changes**: adding a raw metric requires touching `schema.sql`, the INSERT statement + `COLUMNS` list in `mqtt_logger.py`, the `METRICS` list in `rollup.py`, and the `VALID_METRICS` whitelist in `w.py`. A *derived* metric only needs `derived.py` (and optionally the dashboard). `init_db.py` **drops and recreates** the table — never run it against a database with data worth keeping.
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

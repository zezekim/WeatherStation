# WeatherStation

A Raspberry Pi–based environmental monitoring station (JAGASA Environmental Station) that collects weather and air-quality data from a mix of Modbus, UART, and ESPHome sensors, aggregates it over MQTT, logs it to SQLite, and serves a live professional dashboard with derived metrics, air-quality index, threshold alerts, and history charts.

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
                 │ (alerts)                │
                 ▼                         ▼
          pi_hub/alerts/*       w.py (Flask) ──► Dashboard
```

- **`modbus_hub.py`** — Polls RS-485 Modbus wind speed and direction sensors every 2 s and publishes to MQTT under `pi_hub/`. Auto-reconnects on serial/Modbus errors.
- **`pm25_hub.py`** — Reads a PMS particulate sensor over UART (PM1.0 / PM2.5 / PM10) every 5 s and publishes to MQTT.
- **`mqtt_logger.py`** — Subscribes to all topics, normalizes sensor names to a standard schema, snapshots the full state into SQLite every 15 s, and publishes threshold alerts to `pi_hub/alerts/<metric>`.
- **`w.py`** — Flask app and JSON API behind the dashboard.
- **`rollup.py`** — Retention job that compacts old raw rows into hourly averages.

## Derived metrics & indices

Computed on the fly by `derived.py` from the raw sensor columns (no extra storage):

| Output | From | Notes |
|---|---|---|
| Feels-like / heat index | temperature + humidity | NOAA Rothfusz regression |
| Dew point | temperature + humidity | Magnus-Tetens |
| Air Quality Index | PM2.5 + PM10 | US EPA breakpoints, worst-of, with category & color |
| UV category | UV index | WHO bands (Low → Extreme) |
| Wind description | wind speed | Beaufort scale |
| Cardinal direction | wind direction | 16-point compass |
| Pressure trend | pressure now vs ~3 h ago | rising / falling / steady |

## Alerts

`alerts.py` evaluates configurable thresholds (heat index, PM2.5/PM10, UV, wind, pressure — see `config.py`) against the latest reading. Alerts are surfaced on the dashboard and published to MQTT (`pi_hub/alerts/<metric>`, retained, only on state change) by the logger.

## HTTP API

| Endpoint | Returns |
|---|---|
| `GET /data` | Latest reading + all derived fields + `age_seconds`/`is_stale` + active alerts |
| `GET /history/<metric>?hours=&points=` | Downsampled series (bucketed averages + min/max band). `hours` ≤ 720, `points` ≤ 1000 |
| `GET /summary` | Per-metric min/max/avg since local midnight |

`<metric>` is whitelisted against the table columns before use.

## Dashboard

`templates/index.html` is a single self-contained page (Chart.js + a Windy embed, no build step):

- Hero cards: current conditions with feels-like & dew point, a color-coded **AQI badge**, and a live **wind compass**.
- Metric tiles with today's high/low, UV category chip, and a pressure-trend arrow.
- Threshold **alert banner**.
- **Connection status** pill (Live / Stale / Offline) driven by reading age.
- History charts with a **time-range selector** (24 h → 30 d) and shaded min/max bands.
- Light/dark theme.

## Setup

Requires Python 3.11+, an MQTT broker (e.g. Mosquitto), and the sensor hardware. Serial devices are expected at stable udev paths (`/dev/wind_speed`, `/dev/wind_direction`, `/dev/pm25_sensor`).

```bash
python3 -m venv venv
source venv/bin/activate
pip install flask paho-mqtt pymodbus pyserial adafruit-circuitpython-pm25 gunicorn

python init_db.py          # create the DB (WARNING: drops weather_readings)
cp .env.example .env        # then edit: broker, credentials, station lat/lon
```

All scripts read settings from `.env` via `config.py` (stdlib only — no python-dotenv needed). Real environment variables override `.env`. Never commit `.env`.

## Running

Each component runs as its own long-lived process (typically systemd services on the Pi):

```bash
python modbus_hub.py     # wind sensors → MQTT
python pm25_hub.py       # particulate sensor → MQTT
python mqtt_logger.py    # MQTT → SQLite (+ alerts)
python w.py              # or: gunicorn w:app — dashboard on :5000
```

`check_db.py` prints recent rows plus row count, time span, and staleness.

### Retention (cron)

Raw rows accumulate at ~5,800/day. Compact rows older than `RETENTION_DAYS` (default 30) into hourly averages:

```bash
python rollup.py --dry-run     # preview
python rollup.py --vacuum      # compact + reclaim disk
```

Nightly example:

```cron
15 3 * * *  cd /home/pi/weather && venv/bin/python rollup.py --vacuum
```

Rollup is idempotent (only hours with >1 row are touched) and transactional. On a 386-day, 1.29 M-row test database it reduced the file from ~99 MB to ~4 MB.

## Deploying to the Raspberry Pi

The station runs as four **systemd** services (unit files in `systemd/`), all as
user `rs` from `/home/rs/weather` with the project virtualenv:

| Service | Runs |
|---|---|
| `modbus_hub.service` | `modbus_hub.py` — wind sensors |
| `pm25_hub.service`   | `pm25_hub.py` — particulate sensor |
| `mqtt_logger.service`| `mqtt_logger.py` — MQTT → SQLite + alerts |
| `weather.service`    | `gunicorn w:app` — dashboard on `:5000` |

`deploy.sh` decommissions the old version and installs the current one. Run it
**as `rs` (not root)** — it uses `sudo` internally:

```bash
curl -fsSL https://raw.githubusercontent.com/zezekim/WeatherStation/main/deploy.sh -o /tmp/deploy.sh
bash /tmp/deploy.sh        # after the first run it lives at /home/rs/weather/deploy.sh
```

It stops/disables the old services, updates the code from GitHub (a `git reset
--hard` that **preserves `weather_data.db`, `.env`, and `venv/`** — they're
gitignored), syncs dependencies, installs the unit files, and starts everything.
If `.env` isn't configured yet it enables the services but leaves them stopped
and tells you to edit `.env` first. Safe to re-run.

## Database

Single SQLite table `weather_readings` (see `schema.sql`): one row per snapshot with a Unix `timestamp` and one nullable column per raw metric, indexed on `timestamp`.

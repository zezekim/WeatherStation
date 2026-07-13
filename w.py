import sqlite3
import time
from flask import Flask, jsonify, render_template, request

import config
import derived
from alerts import evaluate_alerts

app = Flask(__name__)
DATABASE = 'weather_data.db'

# Metrics that can be charted / summarised. Whitelisted before being
# interpolated into SQL, so this list is the trust boundary — keep it in sync
# with the columns in schema.sql.
VALID_METRICS = [
    'temperature', 'humidity', 'pressure', 'wind_speed', 'wind_direction',
    'uv_index', 'lux', 'voc_index', 'pm1_0', 'pm2_5', 'pm10_0',
]

# A reading older than this (seconds) means the logger or sensors have stalled.
STALE_AFTER = 60


def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def get_weather_outlook(data):
    pressure = data.get('pressure')
    humidity = data.get('humidity')
    wind_speed = data.get('wind_speed')
    if pressure is None or humidity is None or wind_speed is None:
        return "Awaiting complete data..."
    if pressure < 1005:
        return "Low pressure system detected. Expect unsettled or rainy weather."
    if pressure > 1020:
        return "High pressure system dominant. Expect clear and calm weather."
    if humidity > 85:
        return "Air is very humid. Rain is possible."
    if wind_speed > 10:
        return "Conditions are windy. A weather change may be approaching."
    return "Conditions are stable and fair."


def _pressure_reading_near(conn, target_ts):
    """Pressure from the row closest to target_ts (for the 3h trend)."""
    row = conn.execute(
        "SELECT pressure FROM weather_readings "
        "WHERE pressure IS NOT NULL "
        "ORDER BY ABS(timestamp - ?) ASC LIMIT 1",
        (target_ts,),
    ).fetchone()
    return row['pressure'] if row else None


@app.route('/')
def index():
    return render_template(
        'index.html',
        station_name=config.STATION_NAME,
        station_lat=config.STATION_LAT,
        station_lon=config.STATION_LON,
    )


@app.route('/data')
def get_data():
    conn = get_db()
    latest = conn.execute(
        "SELECT * FROM weather_readings ORDER BY timestamp DESC LIMIT 1"
    ).fetchone()

    if not latest:
        conn.close()
        return jsonify({"error": "No data available"}), 404

    data = dict(latest)
    now = int(time.time())

    # Freshness — lets the dashboard show a "stale" / "offline" state instead
    # of presenting a frozen reading as if it were live.
    data['age_seconds'] = max(0, now - int(data['timestamp']))
    data['is_stale'] = data['age_seconds'] > STALE_AFTER

    # Derived fields (dew point, heat index, feels-like, AQI, UV band, ...).
    derived.enrich(data)

    # 3-hour pressure trend.
    past_pressure = _pressure_reading_near(conn, int(data['timestamp']) - 3 * 3600)
    trend, delta = derived.pressure_trend(data.get('pressure'), past_pressure)
    data['pressure_trend'] = trend
    data['pressure_trend_delta'] = delta

    conn.close()

    data['weather_outlook'] = get_weather_outlook(data)
    data['alerts'] = evaluate_alerts(data)
    return jsonify(data)


@app.route('/history/<data_type>')
def get_history(data_type):
    if data_type not in VALID_METRICS:
        return jsonify({"error": "Invalid data type"}), 400

    # Time window and target resolution, both clamped to sane bounds so the
    # endpoint can't be pushed into returning the whole table.
    try:
        hours = int(request.args.get('hours', 72))
    except ValueError:
        hours = 72
    try:
        points = int(request.args.get('points', 300))
    except ValueError:
        points = 300
    hours = max(1, min(hours, 720))       # up to 30 days
    points = max(10, min(points, 1000))

    window = hours * 3600
    now = int(time.time())
    start = now - window
    bucket = max(1, window // points)      # seconds per aggregation bucket

    conn = get_db()
    # Average each bucket into one point: far fewer rows to the browser, and
    # a smoother line. min/max come along for an optional shaded band.
    rows = conn.execute(
        f"""
        SELECT
            CAST(AVG(timestamp) AS INTEGER) AS ts,
            AVG({data_type})  AS avg_v,
            MIN({data_type})  AS min_v,
            MAX({data_type})  AS max_v
        FROM weather_readings
        WHERE {data_type} IS NOT NULL AND timestamp > ? AND timestamp <= ?
        GROUP BY CAST(timestamp AS INTEGER) / ?
        ORDER BY ts ASC
        """,
        (start, now, bucket),
    ).fetchall()
    conn.close()

    return jsonify({
        'metric': data_type,
        'hours': hours,
        'timestamps': [r['ts'] for r in rows],
        'values': [round(r['avg_v'], 2) if r['avg_v'] is not None else None for r in rows],
        'min': [round(r['min_v'], 2) if r['min_v'] is not None else None for r in rows],
        'max': [round(r['max_v'], 2) if r['max_v'] is not None else None for r in rows],
    })


@app.route('/summary')
def get_summary():
    """Per-metric min/max/avg since local midnight, for the 'today' cards."""
    midnight = int(time.mktime(time.localtime()[:3] + (0, 0, 0, 0, 0, -1)))

    agg = ", ".join(
        f"MIN({m}) AS {m}_min, MAX({m}) AS {m}_max, AVG({m}) AS {m}_avg"
        for m in VALID_METRICS
    )
    conn = get_db()
    row = conn.execute(
        f"SELECT COUNT(*) AS n, {agg} FROM weather_readings WHERE timestamp >= ?",
        (midnight,),
    ).fetchone()
    conn.close()

    summary = {'since': midnight, 'samples': row['n']}
    for m in VALID_METRICS:
        summary[m] = {
            'min': round(row[f'{m}_min'], 1) if row[f'{m}_min'] is not None else None,
            'max': round(row[f'{m}_max'], 1) if row[f'{m}_max'] is not None else None,
            'avg': round(row[f'{m}_avg'], 1) if row[f'{m}_avg'] is not None else None,
        }
    return jsonify(summary)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

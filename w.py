import sqlite3
import time # Import the time module
from flask import Flask, jsonify, render_template

app = Flask(__name__)
DATABASE = 'weather_data.db'

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def get_wind_direction_cardinal(degrees):
    if degrees is None: return "N/A"
    directions = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    return directions[round((int(degrees) % 360) / 22.5) % 16]

def get_weather_outlook(data):
    try:
        pressure = data.get('pressure')
        humidity = data.get('humidity')
        wind_speed = data.get('wind_speed')

        if pressure is None or humidity is None or wind_speed is None:
            return "Awaiting complete data..."

        if pressure < 1005:
            return "Low pressure system detected. Expect unsettled or rainy weather."
        elif pressure > 1020:
            return "High pressure system dominant. Expect clear and calm weather."
        elif humidity > 85:
            return "Air is very humid. Rain is possible."
        elif wind_speed > 10:
            return "Conditions are windy. A weather change may be approaching."
        else:
            return "Conditions are stable and fair."
    except (TypeError, ValueError):
        return "Interpreting data..."

@app.route('/')
def index(): return render_template('index.html')

@app.route('/data')
def get_data():
    conn = get_db()
    latest_data = conn.execute("SELECT * FROM weather_readings ORDER BY timestamp DESC LIMIT 1").fetchone()
    conn.close()
    if latest_data:
        data_dict = dict(latest_data)
        data_dict["wind_direction_cardinal"] = get_wind_direction_cardinal(data_dict.get("wind_direction"))
        data_dict["weather_outlook"] = get_weather_outlook(data_dict)
        return jsonify(data_dict)
    return jsonify({"error": "No data available"}), 404

@app.route('/history/<data_type>')
def get_history(data_type):
    valid_types = ['wind_speed', 'wind_direction', 'temperature', 'humidity', 'pressure', 'uv_index', 'lux', 'pm1_0', 'pm2_5', 'pm10_0', 'voc_index']
    if data_type not in valid_types:
        return jsonify({"error": "Invalid data type"}), 400

    conn = get_db()

    # --- THIS IS THE MODIFIED SECTION ---
    # Calculate the timestamp for 72 hours ago
    time_72_hours_ago = int(time.time()) - (72 * 60 * 60)

    # This new query selects all data from the last 72 hours
    # and orders it chronologically for the chart.
    history_data = conn.execute(
        f"SELECT timestamp, {data_type} FROM weather_readings WHERE {data_type} IS NOT NULL AND timestamp > ? ORDER BY timestamp ASC",
        (time_72_hours_ago,)
    ).fetchall()
    # ------------------------------------

    conn.close()

    # We no longer need to reverse the list because the query is now in the correct order
    timestamps = [row['timestamp'] for row in history_data]
    values = [row[data_type] for row in history_data]

    return jsonify({'timestamps': timestamps, 'values': values})
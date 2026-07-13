import paho.mqtt.client as mqtt
import sqlite3
import time
import os
import json
from threading import Lock

from config import MQTT_BROKER, MQTT_PORT, MQTT_USER, MQTT_PASS, require_mqtt
import derived
from alerts import evaluate_alerts

# --- Configuration ---
# Subscribe to everything and filter in on_message: ESPHome node topic prefixes
# aren't known here, so a narrower subscription risks silently dropping a
# sensor. Filtering against TOPIC_MAP below keeps the cost negligible.
MQTT_SUBSCRIBE_TOPIC = "#"
ALERT_TOPIC_PREFIX = "pi_hub/alerts"
SAVE_INTERVAL = 15  # seconds between database snapshots

DATABASE = 'weather_data.db'
db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), DATABASE)

# Maps a topic segment to a standard column name. For ESPHome `/state` topics
# the key is the second-to-last segment; otherwise the last segment.
# Hoisted to module level so it isn't rebuilt on every incoming message.
TOPIC_MAP = {
    # ESPHome sanitized names from the i2c hub
    "temperature": "temperature",
    "humidity": "humidity",
    "pressure": "pressure",
    "ambient_light": "lux",
    "uv_index": "uv_index",
    "voc_index": "voc_index",
    # ESPHome sanitized names from the PMS hub
    "particulate_matter_1_0__m": "pm1_0",
    "particulate_matter_2_5__m": "pm2_5",
    "particulate_matter_10_0__m": "pm10_0",
    # Pi hub custom names
    "wind_speed": "wind_speed",
    "wind_direction": "wind_direction",
}

# Columns written on every snapshot, in INSERT order.
COLUMNS = ["temperature", "humidity", "pressure", "uv_index", "lux",
           "voc_index", "wind_speed", "wind_direction", "pm1_0", "pm2_5", "pm10_0"]

current_state = {}
data_lock = Lock()

# Last published alert level per metric, so we only publish on change.
last_alert_levels = {}


def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        print("Logger: Connected to MQTT Broker!")
        client.subscribe(MQTT_SUBSCRIBE_TOPIC)
    else:
        print(f"Logger: Failed to connect, return code {rc}")


def on_message(client, userdata, msg):
    """Receives any MQTT message and maps it to a standard key."""
    with data_lock:
        try:
            topic = msg.topic
            value_str = msg.payload.decode('utf-8')

            # Extract the key part of the topic.
            sensor_key = topic.split('/')[-2] if topic.endswith('/state') else topic.split('/')[-1]

            if sensor_key in TOPIC_MAP and 'nan' not in value_str:
                standard_key = TOPIC_MAP[sensor_key]
                current_state[standard_key] = float(value_str)
                print(f"Logger: update for '{standard_key}': {value_str}")
        except Exception as e:
            print(f"Logger: Error processing message on topic {msg.topic}: {e}")


def publish_alerts(client, state):
    """Evaluate thresholds and publish alert state changes to MQTT.

    Publishes (retained) to `pi_hub/alerts/<metric>` only when a metric's alert
    level changes — including clearing back to normal — so subscribers aren't
    spammed every snapshot.
    """
    enriched = derived.enrich(dict(state))
    active = {a["metric"]: a for a in evaluate_alerts(enriched)}

    for metric in set(list(active.keys()) + list(last_alert_levels.keys())):
        level = active[metric]["level"] if metric in active else "normal"
        if last_alert_levels.get(metric) == level:
            continue
        last_alert_levels[metric] = level
        payload = json.dumps(active[metric]) if metric in active else json.dumps(
            {"metric": metric, "level": "normal"})
        client.publish(f"{ALERT_TOPIC_PREFIX}/{metric}", payload, retain=True)
        print(f"Logger: ALERT {metric} -> {level}")


def save_state_to_database(client=None):
    """Saves the entire current state to the database and checks alerts."""
    with data_lock:
        state_to_save = current_state.copy()

    if not state_to_save:
        return

    if client is not None:
        try:
            publish_alerts(client, state_to_save)
        except Exception as e:
            print(f"Logger: alert publish failed: {e}")

    try:
        conn = sqlite3.connect(db_path, timeout=10)
        cursor = conn.cursor()

        sql_query = """
        INSERT INTO weather_readings (
            timestamp, temperature, humidity, pressure, uv_index, lux,
            wind_speed, wind_direction, pm1_0, pm2_5, pm10_0, voc_index
        ) VALUES (
            :timestamp, :temperature, :humidity, :pressure, :uv_index, :lux,
            :wind_speed, :wind_direction, :pm1_0, :pm2_5, :pm10_0, :voc_index
        )"""

        state_to_save["timestamp"] = int(time.time())
        for key in COLUMNS:
            state_to_save.setdefault(key, None)

        cursor.execute(sql_query, state_to_save)
        conn.commit()
        conn.close()
        print("--- Logger: Successfully saved full state to database. ---")

    except Exception as e:
        print(f"!!! DATABASE ERROR: {e} !!!")
    # State is deliberately NOT cleared: each snapshot carries the last-known
    # value of every metric.


# --- Main Program ---
if __name__ == "__main__":
    require_mqtt()
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.username_pw_set(MQTT_USER, MQTT_PASS)
    client.on_connect = on_connect
    client.on_message = on_message

    print(f"Connecting to MQTT broker at {MQTT_BROKER}...")
    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    client.loop_start()

    print("MQTT Logger service started.")
    try:
        # Save the current state to the DB every SAVE_INTERVAL seconds.
        while True:
            time.sleep(SAVE_INTERVAL)
            save_state_to_database(client)
    except KeyboardInterrupt:
        print("\nShutting down logger.")
    finally:
        client.loop_stop()

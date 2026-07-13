import paho.mqtt.client as mqtt
import sqlite3
import time
import os
from threading import Lock

from config import MQTT_BROKER, MQTT_PORT, MQTT_USER, MQTT_PASS

# --- Configuration ---
MQTT_SUBSCRIBE_TOPIC = "#"

DATABASE = 'weather_data.db'
db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), DATABASE)

current_state = {}
data_lock = Lock()

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
            # --- THIS IS THE FINAL, CORRECTED TRANSLATION MAP ---
            # It now exactly matches the topics your devices are publishing.
            TOPIC_MAP = {
                # ESPHome sanitized names from your i2c_hub
                "temperature": "temperature",
                "humidity": "humidity",
                "pressure": "pressure",
                "ambient_light": "lux",
                "uv_index": "uv_index",
                "voc_index": "voc_index",

                # ESPHome sanitized names from your pms_hub
                "particulate_matter_1_0__m": "pm1_0",
                "particulate_matter_2_5__m": "pm2_5",
                "particulate_matter_10_0__m": "pm10_0",

                # Pi Hub custom names
                "wind_speed": "wind_speed",
                "wind_direction": "wind_direction"
            }

            topic = msg.topic
            value_str = msg.payload.decode('utf-8')

            # This logic extracts the key part of the topic
            sensor_key_from_topic = topic.split('/')[-2] if topic.endswith('/state') else topic.split('/')[-1]

            if sensor_key_from_topic in TOPIC_MAP and 'nan' not in value_str:
                standard_key = TOPIC_MAP[sensor_key_from_topic]
                current_state[standard_key] = float(value_str)
                print(f"Logger Received update for '{standard_key}': {value_str}")
        except Exception as e:
            print(f"Logger: Error processing message on topic {msg.topic}: {e}")

def save_state_to_database():
    """Saves the entire current state to the database."""
    with data_lock:
        state_to_save = current_state.copy()

    if not state_to_save: return

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
        for key in ["temperature", "humidity", "pressure", "uv_index", "lux", "voc_index", "wind_speed", "wind_direction", "pm1_0", "pm2_5", "pm10_0"]:
            state_to_save.setdefault(key, None)

        cursor.execute(sql_query, state_to_save)
        conn.commit()
        conn.close()
        print("--- Logger: Successfully saved full state to database. ---")

    except Exception as e:
        print(f"!!! DATABASE ERROR: {e} !!!")
    finally:
         # This was the bug from before, now removed. We DO NOT clear the state.
         pass

# --- Main Program ---
if __name__ == "__main__":
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.username_pw_set(MQTT_USER, MQTT_PASS)
    client.on_connect = on_connect
    client.on_message = on_message

    print(f"Connecting to MQTT broker at {MQTT_BROKER}...")
    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    client.loop_start()

    print("MQTT Logger service started.")
    try:
        # We save the current state to the DB every 15 seconds
        while True:
            time.sleep(15) 
            save_state_to_database()
    except KeyboardInterrupt:
        print("\nShutting down logger.")
    finally:
        client.loop_stop()
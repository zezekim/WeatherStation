import time
import serial
import paho.mqtt.client as mqtt
from adafruit_pm25.uart import PM25_UART

from config import MQTT_BROKER, MQTT_PORT, MQTT_USER, MQTT_PASS, require_mqtt

# --- Configuration ---
MQTT_TOPIC_PREFIX = "pi_hub"

# Use our stable USB port name
SERIAL_PORT = "/dev/pm25_sensor"
FETCH_INTERVAL = 5
STARTUP_DELAY = 15 # Still a good idea to wait for the system to be ready

def main():
    require_mqtt()
    print(f"PM2.5 Hub: Script started. Waiting {STARTUP_DELAY} seconds...")
    time.sleep(STARTUP_DELAY)

    # Connect to MQTT Broker
    mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    mqtt_client.username_pw_set(MQTT_USER, MQTT_PASS)
    mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
    mqtt_client.loop_start()
    print("PM2.5 Hub: Connected to MQTT Broker.")

    # Initialize the sensor using pyserial on the dedicated USB port
    uart = serial.Serial(SERIAL_PORT, baudrate=9600, timeout=1)
    pm25 = PM25_UART(uart, None)
    print(f"PM2.5 Hub: Successfully initialized sensor on {SERIAL_PORT}.")

    while True:
        try:
            aqdata = pm25.read()
            # Publish all three standard values
            mqtt_client.publish(f"{MQTT_TOPIC_PREFIX}/pm1_0", f'{aqdata["pm10 standard"]}')
            mqtt_client.publish(f"{MQTT_TOPIC_PREFIX}/pm2_5", f'{aqdata["pm25 standard"]}')
            mqtt_client.publish(f"{MQTT_TOPIC_PREFIX}/pm10_0", f'{aqdata["pm100 standard"]}')
            print(f"PM2.5 Hub: Sent PM2.5 value {aqdata['pm25 standard']}")
        except Exception as e:
            print(f"PM2.5 Hub: Failed to read sensor: {e}")

        time.sleep(FETCH_INTERVAL)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nShutting down PM2.5 Hub.")
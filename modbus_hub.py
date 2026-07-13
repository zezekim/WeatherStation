import inspect
import time
import paho.mqtt.client as mqtt
from pymodbus.client import ModbusSerialClient
from pymodbus.exceptions import ModbusIOException

from config import MQTT_BROKER, MQTT_PORT, MQTT_USER, MQTT_PASS, require_mqtt

# --- Configuration ---
MQTT_TOPIC_PREFIX = "pi_hub"
MODBUS_SLAVE_ID = 1


def _slave_kwarg():
    """Detect the keyword pymodbus uses for the Modbus slave/unit id.

    It has been renamed across releases (unit -> slave -> device_id), so we
    inspect the installed signature instead of hard-coding one name. Returns
    None if none match, in which case we omit it and rely on the library's
    default of 1 (which matches MODBUS_SLAVE_ID)."""
    try:
        params = inspect.signature(ModbusSerialClient.read_holding_registers).parameters
    except (ValueError, TypeError):
        return "slave"
    for name in ("slave", "device_id", "slave_id", "unit"):
        if name in params:
            return name
    return None


SLAVE_KWARG = _slave_kwarg()


def read_holding_register(modbus_client, address):
    """Read one holding register, passing the slave id under whatever keyword
    this pymodbus version expects."""
    kwargs = {"count": 1}
    if SLAVE_KWARG:
        kwargs[SLAVE_KWARG] = MODBUS_SLAVE_ID
    return modbus_client.read_holding_registers(address, **kwargs)

# Define sensors as a list of dictionaries for easier management
SENSORS = [
    {
        "name": "wind_speed",
        "port": "/dev/wind_speed",
        "address": 0,
        "scale": 10.0,
        "unit": "m/s"
    },
    {
        "name": "wind_direction",
        "port": "/dev/wind_direction",
        "address": 1,
        "scale": 1.0, # No division needed
        "unit": "°"
    }
]

MODBUS_BAUD_RATE = 4800
FETCH_INTERVAL = 2

def read_and_publish(mqtt_client, modbus_client, sensor_config):
    """
    Attempts to read data from a Modbus sensor. If it fails,
    it tries to reconnect and read again.
    """
    try:
        if not modbus_client.is_socket_open():
            print(f"Modbus Hub: Reconnecting to {sensor_config['name']}...")
            modbus_client.connect()
            # Give it a moment to establish connection
            time.sleep(1) 

        if not modbus_client.is_socket_open():
            print(f"Modbus Hub: Reconnect failed for {sensor_config['name']}.")
            return

        # Attempt to read the register
        result = read_holding_register(modbus_client, sensor_config['address'])

        if result.isError():
            # This handles Modbus-level errors (e.g., bad CRC, slave not responding)
            raise ModbusIOException(f"Modbus error on {sensor_config['name']}: {result}")

        # If successful, process and publish the data
        raw_value = result.registers[0]
        scaled_value = raw_value / sensor_config['scale']
        
        topic = f"{MQTT_TOPIC_PREFIX}/{sensor_config['name']}"
        payload = f"{scaled_value:.1f}" if sensor_config['scale'] != 1.0 else f"{scaled_value:.0f}"
        
        mqtt_client.publish(topic, payload)
        print(f"Modbus Hub: Sent {sensor_config['name'].replace('_', ' ').title()} {payload}{sensor_config['unit']}")

    except Exception as e:
        print(f"Modbus Hub: An error occurred with {sensor_config['name']}: {e}")
        # An error occurred, so close the connection to force a fresh start on the next loop
        modbus_client.close()

def main():
    require_mqtt()
    mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    mqtt_client.username_pw_set(MQTT_USER, MQTT_PASS)
    mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
    mqtt_client.loop_start()
    print("Modbus Hub: Connected to MQTT Broker.")

    # Create a dictionary to hold our client objects
    modbus_clients = {
        sensor["name"]: ModbusSerialClient(port=sensor["port"], baudrate=MODBUS_BAUD_RATE, timeout=2)
        for sensor in SENSORS
    }
    print("Modbus Hub: Modbus clients initialized.")

    while True:
        for sensor in SENSORS:
            client = modbus_clients[sensor["name"]]
            read_and_publish(mqtt_client, client, sensor)
        
        time.sleep(FETCH_INTERVAL)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nShutting down Modbus Hub.")
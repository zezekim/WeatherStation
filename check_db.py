import sqlite3
import os

DATABASE = 'weather_data.db'

if not os.path.exists(DATABASE):
    print(f"Error: The database file '{DATABASE}' does not exist.")
    exit()

try:
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    print(f"Checking for table 'weather_readings' in '{DATABASE}'...")
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='weather_readings'")
    if cursor.fetchone() is None:
        print("Error: The table 'weather_readings' does not exist in the database.")
        conn.close()
        exit()

    print("Table found. Fetching the 20 most recent rows...")
    cursor.execute("SELECT * FROM weather_readings ORDER BY timestamp DESC LIMIT 20")
    rows = cursor.fetchall()

    if not rows:
        print("\n>>> RESULT: The 'weather_readings' table is currently empty. <<<")
    else:
        print(f"\n>>> RESULT: Found {len(rows)} row(s). Displaying most recent: <<<")
        # Print header (optional, but helpful)
        print("-" * 80)
        print(f"{'ID':<5}{'Timestamp':<20}{'Wind Speed':<15}{'Temp':<10}{'Humidity':<10}{'Pressure':<10}")
        print("-" * 80)
        for row in rows:
            # Assuming standard table structure: id, timestamp, wind_speed, wind_direction, temp, humidity, pressure
            print(f"{row[0]:<5}{row[1]:<20.2f}{row[2]:<15.2f}{row[4]:<10.2f}{row[5]:<10.2f}{row[6]:<10.2f}")

    conn.close()

except sqlite3.Error as e:
    print(f"\nAn SQLite error occurred: {e}")
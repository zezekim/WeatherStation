"""Quick health check: print the most recent rows and basic stats.

Reads by column name and tolerates NULLs, so it keeps working regardless of
column order or gaps in the data.
"""
import sqlite3
import os
import time

DATABASE = 'weather_data.db'
COLUMNS = ["temperature", "humidity", "pressure", "wind_speed",
           "pm2_5", "uv_index"]


def fmt(value, width=10, decimals=1):
    """Right-pad a value, showing '--' for NULLs instead of crashing."""
    text = "--" if value is None else f"{value:.{decimals}f}"
    return f"{text:<{width}}"


def main():
    if not os.path.exists(DATABASE):
        print(f"Error: database file '{DATABASE}' does not exist.")
        return

    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    exists = cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='weather_readings'"
    ).fetchone()
    if not exists:
        print("Error: table 'weather_readings' does not exist.")
        conn.close()
        return

    stats = cur.execute(
        "SELECT COUNT(*) AS n, MIN(timestamp) AS mn, MAX(timestamp) AS mx "
        "FROM weather_readings"
    ).fetchone()
    if not stats['n']:
        print(">>> The 'weather_readings' table is currently empty. <<<")
        conn.close()
        return

    span_days = (stats['mx'] - stats['mn']) / 86400
    age = int(time.time()) - int(stats['mx'])
    print(f"Rows: {stats['n']:,}  |  Span: {span_days:.1f} days  |  "
          f"Latest row age: {age}s {'(STALE)' if age > 60 else '(live)'}")

    rows = cur.execute(
        "SELECT * FROM weather_readings ORDER BY timestamp DESC LIMIT 20"
    ).fetchall()

    print("-" * 88)
    header = f"{'Time':<21}{'Temp':<10}{'Humid':<10}{'Press':<10}{'Wind':<10}{'PM2.5':<10}{'UV':<10}"
    print(header)
    print("-" * 88)
    for row in rows:
        ts = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(row['timestamp']))
        line = f"{ts:<21}" + "".join(fmt(row[c]) for c in COLUMNS)
        print(line)

    conn.close()


if __name__ == "__main__":
    main()

"""Shared database path and schema helpers.

Every process resolves the database to the SAME absolute path (next to this
file), regardless of the working directory it was started from — previously
`w.py` used a bare relative path and would silently create an empty phantom
`weather_data.db` in whatever CWD it happened to run in, then crash on every
query with "no such table".

`ensure_schema()` is non-destructive (CREATE TABLE IF NOT EXISTS), so the
writer can call it on startup without ever dropping existing data.
`connect_ro()` opens read-only, so readers never create a phantom file.
"""
import os
import sqlite3

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'weather_data.db')

# Mirrors schema.sql, but idempotent so it's safe to run against a live DB.
SCHEMA = """
CREATE TABLE IF NOT EXISTS weather_readings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL NOT NULL,
    temperature REAL,
    humidity REAL,
    pressure REAL,
    uv_index REAL,
    lux REAL,
    voc_index REAL,
    wind_speed REAL,
    wind_direction INTEGER,
    pm1_0 REAL,
    pm2_5 REAL,
    pm10_0 REAL
);
CREATE INDEX IF NOT EXISTS idx_timestamp ON weather_readings (timestamp);
"""


def ensure_schema(path=DB_PATH):
    """Create the table and index if they don't exist. Never drops data."""
    conn = sqlite3.connect(path, timeout=10)
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


def connect_ro(path=DB_PATH):
    """Open the database read-only. Raises sqlite3.OperationalError if the file
    doesn't exist (rather than creating an empty one)."""
    conn = sqlite3.connect(f'file:{path}?mode=ro', uri=True)
    conn.row_factory = sqlite3.Row
    return conn

DROP TABLE IF EXISTS weather_readings;

CREATE TABLE weather_readings (
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

CREATE INDEX idx_timestamp ON weather_readings (timestamp);
import sqlite3

DATABASE = 'weather_data.db'
SCHEMA = 'schema.sql'

db = sqlite3.connect(DATABASE)
with open(SCHEMA, mode='r') as f:
    db.cursor().executescript(f.read())
db.commit()
db.close()
print(f"Database '{DATABASE}' has been successfully initialized.")
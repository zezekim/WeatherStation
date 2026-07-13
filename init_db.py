"""Reset the database from schema.sql.

WARNING: schema.sql DROPS the table, so this ERASES all existing data. For
normal startup you don't need this — the logger creates the table
non-destructively via db.ensure_schema(). Use init_db only to deliberately
wipe and recreate.
"""
import os
import sqlite3

import db

SCHEMA = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'schema.sql')

conn = sqlite3.connect(db.DB_PATH)
with open(SCHEMA) as f:
    conn.executescript(f.read())
conn.commit()
conn.close()
print(f"Database '{db.DB_PATH}' has been reset from schema.sql.")

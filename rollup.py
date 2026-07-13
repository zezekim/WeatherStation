"""Data retention / rollup job.

Compacts raw 15-second rows older than RETENTION_DAYS into one hourly-average
row per hour, keeping the database small and the history charts fast while
preserving long-term trends.

Safe to run repeatedly:
  * Only hours containing more than one row are compacted, so an hour that has
    already been rolled up (one row) is skipped — the job is idempotent.
  * All work happens in a single transaction; a failure rolls back cleanly.

Usage:
    python rollup.py                 # compact using RETENTION_DAYS from config
    python rollup.py --dry-run       # report what would change, touch nothing
    python rollup.py --days 60       # override the retention window
    python rollup.py --vacuum        # VACUUM afterwards to reclaim disk space

Intended to run nightly from cron, e.g.:
    15 3 * * *  cd /home/pi/weather && venv/bin/python rollup.py --vacuum
"""
import argparse
import os
import sqlite3
import time

import config

DATABASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'weather_data.db')

METRICS = ["temperature", "humidity", "pressure", "uv_index", "lux",
           "voc_index", "wind_speed", "wind_direction", "pm1_0", "pm2_5", "pm10_0"]


def rollup(db_path, retention_days, dry_run=False, vacuum=False):
    cutoff = int(time.time()) - retention_days * 86400

    conn = sqlite3.connect(db_path, timeout=30)
    cur = conn.cursor()

    # How much is eligible, and how many hours will collapse.
    plan = cur.execute(
        """
        SELECT COUNT(*) AS rows, COUNT(DISTINCT CAST(timestamp/3600 AS INT)) AS hours
        FROM weather_readings
        WHERE timestamp < ?
        """,
        (cutoff,),
    ).fetchone()
    eligible_rows, eligible_hours = plan[0], plan[1]

    compactable = cur.execute(
        """
        SELECT COUNT(*) FROM (
            SELECT 1 FROM weather_readings
            WHERE timestamp < ?
            GROUP BY CAST(timestamp/3600 AS INT)
            HAVING COUNT(*) > 1
        )
        """,
        (cutoff,),
    ).fetchone()[0]

    cutoff_str = time.strftime('%Y-%m-%d %H:%M', time.localtime(cutoff))
    print(f"Retention: {retention_days} days (cutoff {cutoff_str})")
    print(f"Eligible: {eligible_rows:,} rows across {eligible_hours:,} hours")
    print(f"Hours needing compaction (>1 row): {compactable:,}")

    if compactable == 0:
        print("Nothing to do.")
        conn.close()
        return

    if dry_run:
        # Rows after: (eligible_hours) compacted rows + rows already singletons.
        print(f"[dry-run] Would reduce ~{eligible_rows:,} rows to ~{eligible_hours:,} "
              f"(saving ~{eligible_rows - eligible_hours:,} rows). No changes made.")
        conn.close()
        return

    avg_cols = ", ".join(f"AVG({m}) AS {m}" for m in METRICS)
    insert_cols = ", ".join(["timestamp"] + METRICS)
    select_cols = ", ".join(["timestamp"] + METRICS)

    try:
        cur.execute("BEGIN")
        # Aggregate eligible hours (only those with >1 row) into a temp table,
        # stamping each with its hour-start timestamp.
        cur.execute(
            f"""
            CREATE TEMP TABLE _rollup AS
            SELECT CAST(timestamp/3600 AS INT) * 3600 AS timestamp, {avg_cols}
            FROM weather_readings
            WHERE timestamp < ?
            GROUP BY CAST(timestamp/3600 AS INT)
            HAVING COUNT(*) > 1
            """,
            (cutoff,),
        )
        # Delete only the raw rows belonging to hours we're compacting, so
        # already-singleton hours are left untouched.
        cur.execute(
            """
            DELETE FROM weather_readings
            WHERE timestamp < ?
              AND CAST(timestamp/3600 AS INT) IN (SELECT timestamp/3600 FROM _rollup)
            """,
            (cutoff,),
        )
        deleted = cur.rowcount
        cur.execute(
            f"INSERT INTO weather_readings ({insert_cols}) SELECT {select_cols} FROM _rollup"
        )
        inserted = cur.rowcount
        cur.execute("DROP TABLE _rollup")
        conn.commit()
        print(f"Compacted {deleted:,} rows into {inserted:,} hourly rows "
              f"(net -{deleted - inserted:,}).")
    except Exception as e:
        conn.rollback()
        print(f"Rollup failed, rolled back: {e}")
        conn.close()
        raise

    if vacuum:
        print("Vacuuming database to reclaim space...")
        conn.execute("VACUUM")
        print("Vacuum complete.")

    conn.close()


def main():
    parser = argparse.ArgumentParser(description="Compact old readings into hourly averages.")
    parser.add_argument("--days", type=int, default=config.RETENTION_DAYS,
                        help=f"retention window in days (default {config.RETENTION_DAYS})")
    parser.add_argument("--dry-run", action="store_true", help="report only, change nothing")
    parser.add_argument("--vacuum", action="store_true", help="VACUUM after compacting")
    parser.add_argument("--db", default=DATABASE, help="path to the database file")
    args = parser.parse_args()

    rollup(args.db, args.days, dry_run=args.dry_run, vacuum=args.vacuum)


if __name__ == "__main__":
    main()

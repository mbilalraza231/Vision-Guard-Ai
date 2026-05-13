#!/usr/bin/env python3
"""
Clear all data from the VisionGuard AI events database.

One-time admin script to remove false positive events and stale data.
Does NOT drop or recreate tables — only deletes rows and vacuums.

Usage:
    python clear_db.py
    VG_DB_PATH=/path/to/events.db python clear_db.py
"""

import os
import sys


def main():
    host = os.environ.get("VG_POSTGRES_HOST", "localhost")
    user = os.environ.get("VG_POSTGRES_USER", "postgres")
    db_name = os.environ.get("VG_POSTGRES_DB", "visionguard")
    password = os.environ.get("VG_POSTGRES_PASSWORD", "postgres")

    print(f"Connecting to PostgreSQL: {host} (DB: {db_name})")

    try:
        import psycopg2
        conn = psycopg2.connect(
            host=host,
            user=user,
            password=password,
            dbname=db_name
        )
        cursor = conn.cursor()

        tables = ["alerts", "event_evidence", "events"]

        # --- Before counts ---
        print("\n--- Before cleanup ---")
        for table in tables:
            try:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                count = cursor.fetchone()[0]
                print(f"  {table}: {count} rows")
            except Exception as e:
                print(f"  {table}: error ({e})")

        # --- Truncate (FK handling: CASCADE or specific order) ---
        print("\n--- Truncating tables ---")
        # In Postgres, TRUNCATE ... CASCADE is safest for related tables
        cursor.execute("TRUNCATE TABLE alerts, event_evidence, events RESTART IDENTITY CASCADE")
        print("  Truncate command executed.")

        conn.commit()

        # --- After counts ---
        print("\n--- After cleanup ---")
        for table in tables:
            try:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                count = cursor.fetchone()[0]
                print(f"  {table}: {count} rows")
            except Exception as e:
                print(f"  {table}: error")

        conn.close()
        print("\nDatabase cleared successfully.")
    except ImportError:
        print("ERROR: psycopg2 package not installed.")
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

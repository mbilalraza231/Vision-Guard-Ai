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
import sqlite3
import sys


def main():
    db_path = os.environ.get("VG_DB_PATH", "/data/visionguard/events.db")

    print(f"Database path: {db_path}")

    if not os.path.exists(db_path):
        print(f"ERROR: Database file does not exist: {db_path}")
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    tables = ["alerts", "event_evidence", "events"]

    # --- Before counts ---
    print("\n--- Before cleanup ---")
    for table in tables:
        try:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            print(f"  {table}: {count} rows")
        except sqlite3.OperationalError:
            print(f"  {table}: table does not exist (skipping)")

    # --- Delete rows (FK order: alerts, event_evidence, then events) ---
    print("\n--- Deleting rows ---")
    for table in tables:
        try:
            cursor.execute(f"DELETE FROM {table}")
            deleted = cursor.rowcount
            print(f"  {table}: deleted {deleted} rows")
        except sqlite3.OperationalError:
            print(f"  {table}: table does not exist (skipping)")

    conn.commit()

    # --- Vacuum ---
    print("\n--- Vacuuming database ---")
    cursor.execute("VACUUM")
    print("  Done")

    # --- After counts ---
    print("\n--- After cleanup ---")
    for table in tables:
        try:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            print(f"  {table}: {count} rows")
        except sqlite3.OperationalError:
            print(f"  {table}: table does not exist")

    conn.close()
    print("\nDatabase cleared successfully.")


if __name__ == "__main__":
    main()

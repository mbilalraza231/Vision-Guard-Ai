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
        cur = conn.cursor()

        # Fix snapshots
        cur.execute("""
            UPDATE event_evidence 
            SET public_url = REPLACE(public_url, '/data/visionguard/detections/', 'http://localhost:8000/detections/images/') 
            WHERE storage_provider = 'local' AND public_url LIKE '/data/visionguard/detections/%'
        """)
        snapshot_count = cur.rowcount

        # Fix clips
        cur.execute("""
            UPDATE event_evidence 
            SET public_url = REPLACE(public_url, '/data/visionguard/clips/', 'http://localhost:8000/detections/clips/') 
            WHERE storage_provider = 'local' AND public_url LIKE '/data/visionguard/clips/%'
        """)
        clip_count = cur.rowcount

        conn.commit()
        print(f"✅ Cleanup complete. Fixed {snapshot_count} snapshot paths and {clip_count} clip paths.")
        conn.close()
    except ImportError:
        print("ERROR: psycopg2 package not installed.")
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()

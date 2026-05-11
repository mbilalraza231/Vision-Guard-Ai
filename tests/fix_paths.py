import sqlite3
import os

db_path = '/data/visionguard/events.db'
if not os.path.exists(db_path):
    print(f"Database not found at {db_path}")
    exit(1)

conn = sqlite3.connect(db_path)
cur = conn.cursor()

# Fix snapshots
cur.execute("UPDATE event_evidence SET public_url = REPLACE(public_url, '/data/visionguard/detections/', 'http://localhost:8000/detections/images/') WHERE storage_provider = 'local' AND public_url LIKE '/data/visionguard/detections/%'")

# Fix clips
cur.execute("UPDATE event_evidence SET public_url = REPLACE(public_url, '/data/visionguard/clips/', 'http://localhost:8000/detections/clips/') WHERE storage_provider = 'local' AND public_url LIKE '/data/visionguard/clips/%'")

print(f"✅ Cleanup complete. Fixed {conn.total_changes} old evidence paths.")

conn.commit()
conn.close()

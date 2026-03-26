import sqlite3
from config import DB_PATH

db_path = DB_PATH
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Add drive_token column if it doesn't exist
cursor.execute('PRAGMA table_info(users)')
columns = [row[1] for row in cursor.fetchall()]
if 'drive_token' not in columns:
    cursor.execute('ALTER TABLE users ADD COLUMN drive_token TEXT')
    conn.commit()
    print("Added drive_token column to users table.")
else:
    print("drive_token column already exists.")

conn.close()

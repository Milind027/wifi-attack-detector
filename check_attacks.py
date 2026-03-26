import sqlite3
from config import DB_PATH

db_path = DB_PATH
conn = sqlite3.connect(db_path)
cursor = conn.cursor()
cursor.execute("SELECT * FROM attacks")
logs = cursor.fetchall()
print(f"Found {len(logs)} attacks in database:")
for log in logs:
    print(log)
conn.close()

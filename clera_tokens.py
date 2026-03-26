import sqlite3
from config import DB_PATH

db_path = DB_PATH
conn = sqlite3.connect(db_path)
cursor = conn.cursor()
cursor.execute("UPDATE users SET drive_token = NULL")
conn.commit()
conn.close()
print("Cleared all drive tokens.")

import sqlite3
import logging
import os
import csv
from logging.handlers import RotatingFileHandler
from bcrypt import hashpw, gensalt, checkpw
from cryptography.fernet import Fernet
from config import PROJECT_DIR, DB_PATH, KEY_PATH, LOG_PATH, LOG_LEVEL, LOG_MAX_BYTES, LOG_BACKUP_COUNT

# Configure logging with size-based rotation
log_dir = PROJECT_DIR
log_path = LOG_PATH
os.makedirs(log_dir, exist_ok=True)
logger = logging.getLogger()
if not logger.handlers:
    logger.setLevel(getattr(logging, LOG_LEVEL, logging.DEBUG))
    handler = RotatingFileHandler(log_path, maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUP_COUNT)
    handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    logger.addHandler(handler)

class Database:
    def __init__(self, db_path=DB_PATH):
        self.conn = sqlite3.connect(db_path)
        self.cursor = self.conn.cursor()
        key_file = KEY_PATH
        if os.getenv("ENCRYPTION_KEY"):
            self.encryption_key = os.getenv("ENCRYPTION_KEY").encode()
        else:
            if os.path.exists(key_file):
                with open(key_file, "rb") as f:
                    self.encryption_key = f.read()
            else:
                self.encryption_key = Fernet.generate_key()
                with open(key_file, "wb") as f:
                    f.write(self.encryption_key)
        self.cipher = Fernet(self.encryption_key)
        self.attack_buffer = []
        self.buffer_limit = 100
        self.create_tables()
        logging.debug("Database initialized")

    def create_tables(self):
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS attacks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                src_mac TEXT,
                dst_mac TEXT,
                ssid TEXT,
                attack_type TEXT DEFAULT 'deauth',
                severity TEXT DEFAULT 'medium'
            )
        ''')
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE,
                password TEXT,
                sender_email TEXT,
                sender_password TEXT,
                receiver_email TEXT,
                smtp_host TEXT DEFAULT 'smtp.gmail.com',
                smtp_port INTEGER DEFAULT 587,
                drive_token TEXT
            )
        ''')
        self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_timestamp ON attacks (timestamp)')
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS threat_flags (
                mac TEXT PRIMARY KEY,
                label TEXT DEFAULT '',
                flagged_at TEXT
            )
        ''')
        # Migration: add new columns to existing databases
        self.cursor.execute('PRAGMA table_info(attacks)')
        columns = [row[1] for row in self.cursor.fetchall()]
        if 'attack_type' not in columns:
            self.cursor.execute("ALTER TABLE attacks ADD COLUMN attack_type TEXT DEFAULT 'deauth'")
        if 'severity' not in columns:
            self.cursor.execute("ALTER TABLE attacks ADD COLUMN severity TEXT DEFAULT 'medium'")
        self.conn.commit()
        logging.debug("Database tables created")

    def log_attack(self, attack):
        self.attack_buffer.append(attack)
        logging.debug(f"Buffered attack: {attack}")
        if len(self.attack_buffer) >= self.buffer_limit:
            self.flush_attacks()

    def flush_attacks(self):
        if self.attack_buffer:
            self.cursor.executemany(
                'INSERT INTO attacks (timestamp, src_mac, dst_mac, ssid, attack_type, severity) VALUES (?, ?, ?, ?, ?, ?)',
                [(a["timestamp"], a["src_mac"], a["dst_mac"], a["ssid"],
                  a.get("attack_type", "deauth"), a.get("severity", "medium")) for a in self.attack_buffer])
            self.conn.commit()
            logging.info(f"Logged {len(self.attack_buffer)} attacks to database")
            self.attack_buffer = []

    def get_recent_logs(self, limit=10):
        self.flush_attacks()
        self.cursor.execute('SELECT * FROM attacks ORDER BY timestamp DESC LIMIT ?', (limit,))
        logs = self.cursor.fetchall()
        logging.debug(f"Fetched {len(logs)} recent logs")
        return logs

    def get_all_logs(self):
        self.flush_attacks()
        self.cursor.execute('SELECT * FROM attacks ORDER BY timestamp DESC')
        logs = self.cursor.fetchall()
        logging.debug(f"Fetched {len(logs)} logs")
        return logs

    def export_to_csv(self, csv_path):
        self.flush_attacks()  # Ensure all buffered attacks are saved
        logs = self.get_all_logs()
        logging.debug(f"Exporting {len(logs)} logs to {csv_path}")
        with open(csv_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["Timestamp", "Source MAC", "Target MAC", "SSID", "Attack Type", "Severity"])
            for log in logs:
                writer.writerow([log[1], log[2], log[3], log[4],
                                 log[5] if len(log) > 5 else "deauth",
                                 log[6] if len(log) > 6 else "medium"])
        logging.info(f"Exported {len(logs)} logs to {csv_path}")

    def add_user(self, username, password, receiver_email, sender_email=None, sender_password=None):
        hashed_pw = hashpw(password.encode(), gensalt()).decode()
        receiver_email = receiver_email or sender_email
        encrypted_password = self.cipher.encrypt(sender_password.encode()).decode() if sender_password else None
        try:
            self.cursor.execute('INSERT INTO users (username, password, sender_email, sender_password, receiver_email) '
                               'VALUES (?, ?, ?, ?, ?)', (username, hashed_pw, sender_email, encrypted_password, receiver_email))
            self.conn.commit()
            logging.info(f"Added user: {username}")
            return True
        except sqlite3.IntegrityError:
            logging.warning(f"Failed to add user: {username} or {receiver_email} already exists")
            return False

    def verify_user(self, login_input, password):
        self.cursor.execute('SELECT password FROM users WHERE username = ? OR receiver_email = ?',
                           (login_input, login_input))
        result = self.cursor.fetchone()
        if result and isinstance(result[0], str):
            try:
                return checkpw(password.encode(), result[0].encode())
            except ValueError as e:
                logging.error(f"Invalid password hash for {login_input}: {e}")
                return False
        logging.warning(f"No user found for {login_input}")
        return False

    def get_username_by_login(self, login_input):
        self.cursor.execute('SELECT username FROM users WHERE username = ? OR receiver_email = ?',
                           (login_input, login_input))
        result = self.cursor.fetchone()
        username = result[0] if result else None
        logging.debug(f"Got username {username} for login {login_input}")
        return username

    def update_username(self, old_username, new_username):
        try:
            self.cursor.execute('UPDATE users SET username = ? WHERE username = ?', (new_username, old_username))
            self.conn.commit()
            logging.info(f"Updated username from {old_username} to {new_username}")
            return self.cursor.rowcount > 0
        except sqlite3.IntegrityError:
            logging.warning(f"Failed to update username to {new_username}: already exists")
            return False

    def update_password(self, username, new_password):
        hashed_pw = hashpw(new_password.encode(), gensalt()).decode()
        self.cursor.execute('UPDATE users SET password = ? WHERE username = ?', (hashed_pw, username))
        self.conn.commit()
        logging.info(f"Updated password for {username}")
        return self.cursor.rowcount > 0

    def update_email_config(self, username, sender_email, sender_password, receiver_email, smtp_host='smtp.gmail.com', smtp_port=587):
        encrypted_password = self.cipher.encrypt(sender_password.encode()).decode() if sender_password else None
        try:
            if sender_email is None and sender_password is None:
                self.cursor.execute('UPDATE users SET receiver_email = ? WHERE username = ?', (receiver_email, username))
            else:
                self.cursor.execute('UPDATE users SET sender_email = ?, sender_password = ?, receiver_email = ?, smtp_host = ?, smtp_port = ? '
                                   'WHERE username = ?', (sender_email, encrypted_password, receiver_email, smtp_host, smtp_port, username))
            self.conn.commit()
            logging.info(f"Updated email config for {username}")
            return self.cursor.rowcount > 0
        except sqlite3.IntegrityError:
            logging.warning(f"Failed to update email config for {username}: {receiver_email} already in use")
            return False

    def get_email_config_by_login(self, login_input):
        self.cursor.execute('SELECT smtp_host, smtp_port, sender_email, sender_password, receiver_email FROM users WHERE username = ? OR receiver_email = ?',
                           (login_input, login_input))
        result = self.cursor.fetchone()
        if result:
            decrypted_password = self.cipher.decrypt(result[3].encode()).decode() if result[3] else None
            logging.debug(f"Got email config for {login_input}")
            return {'host': result[0], 'port': result[1]}, result[2], decrypted_password, result[4]
        logging.warning(f"No email config for {login_input}")
        return None

    def get_email_config(self, username):
        self.cursor.execute('SELECT smtp_host, smtp_port, sender_email, sender_password, receiver_email FROM users WHERE username = ?',
                           (username,))
        result = self.cursor.fetchone()
        if result:
            decrypted_password = self.cipher.decrypt(result[3].encode()).decode() if result[3] else None
            logging.debug(f"Got email config for {username}")
            return {'host': result[0], 'port': result[1]}, result[2], decrypted_password, result[4]
        logging.warning(f"No email config for {username}")
        return None

    def store_drive_token(self, username, token):
        encrypted_token = self.cipher.encrypt(token.encode()).decode()
        self.cursor.execute('UPDATE users SET drive_token = ? WHERE username = ?', (encrypted_token, username))
        self.conn.commit()
        logging.info(f"Stored Drive token for {username}")

    def get_drive_token(self, username):
        self.cursor.execute('SELECT drive_token FROM users WHERE username = ?', (username,))
        result = self.cursor.fetchone()
        if result and result[0]:
            return self.cipher.decrypt(result[0].encode()).decode()
        return None

    def clear_drive_token(self, username):
        self.cursor.execute('UPDATE users SET drive_token = NULL WHERE username = ?', (username,))
        self.conn.commit()
        logging.info(f"Cleared Drive token for {username}")

    def close(self):
        self.flush_attacks()
        self.conn.close()
        logging.info("Database connection closed")

    # ── Threat flagging ────────────────────────────────────────

    def flag_threat(self, mac: str, label: str = ""):
        """Flag a MAC address as a persistent threat."""
        import time
        mac = mac.upper().strip()
        self.cursor.execute(
            'INSERT OR REPLACE INTO threat_flags (mac, label, flagged_at) VALUES (?, ?, ?)',
            (mac, label, time.strftime('%Y-%m-%d %H:%M:%S'))
        )
        self.conn.commit()
        logging.info(f"Flagged threat: {mac} ({label})")

    def unflag_threat(self, mac: str):
        """Remove threat flag from a MAC address."""
        mac = mac.upper().strip()
        self.cursor.execute('DELETE FROM threat_flags WHERE mac = ?', (mac,))
        self.conn.commit()
        logging.info(f"Unflagged threat: {mac}")

    def get_flagged_threats(self) -> list:
        """Return all flagged MACs as list of (mac, label, flagged_at)."""
        self.cursor.execute('SELECT mac, label, flagged_at FROM threat_flags ORDER BY flagged_at DESC')
        return self.cursor.fetchall()

    def is_flagged(self, mac: str) -> bool:
        """Check if a MAC address is flagged as a threat."""
        mac = mac.upper().strip()
        self.cursor.execute('SELECT 1 FROM threat_flags WHERE mac = ?', (mac,))
        return self.cursor.fetchone() is not None

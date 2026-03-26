import sys
import logging
import os
from logging.handlers import RotatingFileHandler
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QTimer
from auth import LoginDialog
from gui import WiFiMonitorGUI
from wifi_detector import WiFiDetector
from drive_uploader import DriveUploader
from config import PROJECT_DIR, LOG_PATH, LOG_LEVEL, LOG_MAX_BYTES, LOG_BACKUP_COUNT

# Configure logging with size-based rotation
log_dir = PROJECT_DIR
log_path = LOG_PATH
os.makedirs(log_dir, exist_ok=True)
logger = logging.getLogger()
logger.setLevel(getattr(logging, LOG_LEVEL, logging.DEBUG))
handler = RotatingFileHandler(log_path, maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUP_COUNT)
handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
logger.addHandler(handler)

# Set environment variables to avoid dconf issues
os.environ["HOME"] = os.path.expanduser("~")
os.environ["XDG_RUNTIME_DIR"] = f"/tmp/runtime-{os.getenv('USER', 'root')}"
os.makedirs(os.environ["XDG_RUNTIME_DIR"], exist_ok=True)
os.environ["XDG_CONFIG_HOME"] = os.path.join(os.environ["HOME"], ".config")

# Force Qt to use xcb platform
os.environ["QT_QPA_PLATFORM"] = "xcb"

# Suppress Qt warnings
os.environ["QT_LOGGING_RULES"] = "qt5.xkb.warning=false"

if __name__ == "__main__":
    app = QApplication(sys.argv)
    logging.info("Application started")

    # Initialize DriveUploader
    drive_uploader = DriveUploader()

    # Timer to upload logs every hour (3600000 ms)
    upload_timer = QTimer()
    upload_timer.timeout.connect(lambda: drive_uploader.upload_logs(None, log_dir))
    upload_timer.start(3600000)

    while True:
        login = LoginDialog()
        if login.exec_():
            detector = WiFiDetector(username=login.username)
            window = WiFiMonitorGUI(detector, login.username, drive_uploader)
            window.show()
            logging.info(f"Main window opened for user: {login.username}")
            drive_uploader.set_username(login.username)
            app.aboutToQuit.connect(lambda: drive_uploader.upload_logs(login.username, log_dir))
            sys.exit(app.exec_())
        else:
            logging.info("Login dialog closed without login")
            drive_uploader.upload_logs(None, log_dir)
            break

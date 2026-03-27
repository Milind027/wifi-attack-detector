import smtplib
import time
import logging
import os
from logging.handlers import RotatingFileHandler
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Configure logging with size-based rotation
from config import PROJECT_DIR, LOG_PATH, LOG_LEVEL, LOG_MAX_BYTES, LOG_BACKUP_COUNT
log_dir = PROJECT_DIR
log_path = LOG_PATH
os.makedirs(log_dir, exist_ok=True)
logger = logging.getLogger()
if not logger.handlers:
    logger.setLevel(getattr(logging, LOG_LEVEL, logging.DEBUG))
    handler = RotatingFileHandler(log_path, maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUP_COUNT)
    handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    logger.addHandler(handler)

class WiFiNotifier:
    def __init__(self, smtp_config, sender_email, sender_password, receiver_email):
        self.smtp_host = smtp_config['host']
        self.smtp_port = smtp_config['port']
        self.sender_email = sender_email
        self.sender_password = sender_password
        self.receiver_email = receiver_email
        self.last_sent = 0.0
        self.attack_buffer = []
        self.debounce_interval = 0
        logging.debug(f"WiFiNotifier initialized for {sender_email}")

    def send_email(self, subject, body):
        logging.debug(f"send_email called with subject: {subject}, body: {body}")
        self.attack_buffer.append(body)
        current_time = time.time()
        if current_time - self.last_sent >= self.debounce_interval and self.attack_buffer:
            combined_body = "\n".join(self.attack_buffer)
            self.attack_buffer = []
            self.last_sent = current_time

            msg = MIMEMultipart()
            msg['From'] = self.sender_email
            msg['To'] = self.receiver_email
            msg['Subject'] = subject

            if '|' in combined_body:
                rows = ""
                for b in combined_body.split("\n"):
                    if not b:
                        continue
                    parts = [p.strip() for p in b.split('|')]
                    if len(parts) >= 4:
                        rows += f"<tr><td>{parts[0]}</td><td>{parts[1]}</td><td>{parts[2]}</td><td>{parts[3]}</td></tr>"
                    else:
                        rows += f"<tr><td colspan='4'>{b}</td></tr>"
                html = f"""
                <html>
                    <body>
                        <h2>{subject}</h2>
                        <table border="1">
                            <tr><th>Timestamp</th><th>Source MAC</th><th>Target MAC</th><th>SSID</th></tr>
                            {rows}
                        </table>
                    </body>
                </html>
                """
            else:
                html = f"""
                <html>
                    <body>
                        <h2>{subject}</h2>
                        <p>{combined_body}</p>
                    </body>
                </html>
                """
            msg.attach(MIMEText(html, 'html'))

            try:
                logging.debug(f"Attempting SMTP connection to {self.smtp_host}:{self.smtp_port}")
                with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                    server.starttls()
                    logging.debug(f"Logging in with {self.sender_email}")
                    server.login(self.sender_email, self.sender_password)
                    server.sendmail(self.sender_email, self.receiver_email, msg.as_string())
                    logging.info(f"Email sent to {self.receiver_email}: {subject}")
            except Exception as e:
                logging.error(f"Failed to send email to {self.receiver_email}: {e}")


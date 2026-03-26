# 🛡️ WiFi Attack Detector

A Linux-based cybersecurity tool that detects WiFi deauthentication attacks in real-time using Scapy and PyQt5.

## Features

- **Real-time detection** — Deauth floods, evil twin APs, PMKID harvesting, probe/beacon floods
- **Multi-channel alerts** — Email (Gmail), Telegram, ntfy.sh, Twilio SMS
- **Modern GUI** — Dashboard, searchable logs, network map, analytics, dark/light theme
- **System tray** — Minimize to tray for background monitoring
- **Export** — CSV and styled PDF attack reports
- **MAC vendor lookup** — Identify device manufacturers from MAC addresses
- **Threat flagging** — Right-click to flag suspicious MACs (persistent, stored in DB)
- **Encrypted storage** — Passwords and tokens encrypted with Fernet
- **Google Drive backup** — Auto-upload logs to the cloud

## Requirements

- **Linux** with a WiFi adapter that supports **monitor mode**
- **Python 3.8+**
- **Root privileges** (required for monitor mode and packet sniffing)
- `aircrack-ng` suite

## Installation

### 1. Clone the repo

```bash
git clone https://github.com/yourusername/wifi-attack-detector.git
cd wifi-attack-detector
```

### 2. Install system dependencies

```bash
sudo ./install.sh
```

### 3. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure secrets

```bash
cp .env.example .env
```

Edit `.env` with your credentials:

```env
# Gmail SMTP
SENDER_EMAIL=your_email@gmail.com
SENDER_PASSWORD=your_gmail_app_password

# Telegram Bot (from @BotFather)
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id

# ntfy.sh
NTFY_TOPIC=https://ntfy.sh/your-unique-topic

# Twilio SMS
TWILIO_ACCOUNT_SID=your_account_sid
TWILIO_AUTH_TOKEN=your_auth_token
TWILIO_FROM_NUMBER=+1234567890
TWILIO_TO_NUMBER=+0987654321
```

> **Gmail App Password:** Go to [Google App Passwords](https://myaccount.google.com/apppasswords) and generate a 16-character app password.

### 5. (Optional) Google Drive backup

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project → Enable **Google Drive API**
3. Create **OAuth 2.0 Client ID** (Desktop app)
4. Download the JSON and save as `credentials.json` in project root

> **Do NOT commit `credentials.json` to Git.** It's already in `.gitignore`.

### 6. Run

```bash
sudo python main.py
```

## Usage

1. **Login/Register** — Create an account on first run
2. **Start Monitoring** — Click the button to begin packet capture
3. **Dashboard** — View live attack stats and recent logs
4. **Logs** — Search, filter by type/severity, export to CSV or PDF
5. **Network Map** — See nearby APs with vendor, signal, encryption info
6. **Analytics** — Top attackers, attack type breakdown, hourly distribution
7. **Settings** — Adjust thresholds, configure email, toggle alert channels

Alert channels can be enabled/disabled at runtime from **Settings → Alert Channels** — no restart needed.

## Project Structure

```
├── main.py                 # Entry point
├── gui.py                  # PyQt5 GUI (dashboard, logs, network map, analytics, settings)
├── wifi_detector.py        # Detection engine (Scapy sniffer)
├── database.py             # SQLite database (attacks, users, threat flags)
├── config.py               # Config loader (.env + YAML)
├── config.yaml             # Non-sensitive settings (thresholds, interface)
├── mail.py                 # Email notifier
├── telegram_notifier.py    # Telegram notifier
├── ntfy_notifier.py        # ntfy.sh notifier
├── twilio_notifier.py      # Twilio SMS notifier
├── oui_lookup.py           # MAC vendor OUI database
├── auth.py                 # Login/registration
├── drive_uploader.py       # Google Drive backup
├── .env.example            # Secrets template
├── .gitignore              # Excludes .env, credentials, DB, logs
├── requirements.txt        # Python dependencies
└── install.sh              # System dependency installer
```

## Testing

```bash
python -m unittest test_threshold test_evil_twin -v
```

```
Ran 16 tests in 0.003s
OK
```

## Security Notes

- All secrets are stored in `.env` (git-ignored) and loaded via `python-dotenv`
- User passwords are hashed with `bcrypt`
- Email passwords and Drive tokens are encrypted with `Fernet`
- `.env`, `credentials.json`, `encryption.key`, and `*.db` are excluded from Git

## License

MIT

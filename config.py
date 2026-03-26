"""
Centralized configuration loader for WiFi Attack Detector.
Loads settings from config.yaml and provides easy access to all paths and settings.
"""

import os
import yaml

# Locate config.yaml relative to this file (project root)
_CONFIG_DIR = os.path.dirname(os.path.abspath(__file__))
_CONFIG_PATH = os.path.join(_CONFIG_DIR, "config.yaml")


def _load_config() -> dict:
    """Load and return the config.yaml as a dictionary."""
    if not os.path.exists(_CONFIG_PATH):
        raise FileNotFoundError(
            f"config.yaml not found at {_CONFIG_PATH}. "
            "Copy config.yaml.example to config.yaml and update it for your system."
        )
    with open(_CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)


# Load once at import time
CONFIG = _load_config()

# --- Derived convenience values ---

# Base project directory
PROJECT_DIR: str = CONFIG["paths"]["project_dir"]

# Ensure the project directory exists
os.makedirs(PROJECT_DIR, exist_ok=True)

# Full paths to key files
DB_PATH: str = os.path.join(PROJECT_DIR, CONFIG["paths"]["database"])
KEY_PATH: str = os.path.join(PROJECT_DIR, CONFIG["paths"]["encryption_key"])
CREDENTIALS_PATH: str = os.path.join(PROJECT_DIR, CONFIG["paths"]["credentials_file"])
LOG_PATH: str = os.path.join(PROJECT_DIR, CONFIG["paths"]["log_file"])

# WiFi settings
DEFAULT_INTERFACE: str = CONFIG.get("wifi", {}).get("interface", "wlan0")

# Logging settings
LOG_LEVEL: str = CONFIG.get("logging", {}).get("level", "DEBUG")
LOG_MAX_BYTES: int = CONFIG.get("logging", {}).get("max_bytes", 10485760)  # 10 MB
LOG_BACKUP_COUNT: int = CONFIG.get("logging", {}).get("backup_count", 3)

# Threshold settings
DEAUTH_THRESHOLD_COUNT: int = CONFIG.get("threshold", {}).get("deauth_count", 10)
DEAUTH_THRESHOLD_WINDOW: int = CONFIG.get("threshold", {}).get("deauth_window", 5)

# Evil Twin detection settings
EVIL_TWIN_ENABLED: bool = CONFIG.get("evil_twin", {}).get("enabled", True)
EVIL_TWIN_TRUSTED_APS: list = CONFIG.get("evil_twin", {}).get("trusted_aps", None) or []

# Probe request flood detection settings
PROBE_FLOOD_ENABLED: bool = CONFIG.get("probe_flood", {}).get("enabled", True)
PROBE_FLOOD_COUNT: int = CONFIG.get("probe_flood", {}).get("count", 50)
PROBE_FLOOD_WINDOW: int = CONFIG.get("probe_flood", {}).get("window", 10)

# Beacon flood detection settings
BEACON_FLOOD_ENABLED: bool = CONFIG.get("beacon_flood", {}).get("enabled", True)
BEACON_FLOOD_COUNT: int = CONFIG.get("beacon_flood", {}).get("count", 100)
BEACON_FLOOD_WINDOW: int = CONFIG.get("beacon_flood", {}).get("window", 5)

# PMKID attack detection settings
PMKID_ENABLED: bool = CONFIG.get("pmkid", {}).get("enabled", True)
PMKID_COUNT: int = CONFIG.get("pmkid", {}).get("count", 5)
PMKID_WINDOW: int = CONFIG.get("pmkid", {}).get("window", 10)

# Telegram alert settings (secrets from .env, flags from YAML)
TELEGRAM_ENABLED: bool = CONFIG.get("telegram", {}).get("enabled", False)
TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN") or CONFIG.get("telegram", {}).get("bot_token", "")
TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID") or str(CONFIG.get("telegram", {}).get("chat_id", ""))

# ntfy.sh push notification settings (secrets from .env, flags from YAML)
NTFY_ENABLED: bool = CONFIG.get("ntfy", {}).get("enabled", False)
NTFY_TOPIC: str = os.getenv("NTFY_TOPIC") or CONFIG.get("ntfy", {}).get("topic", "")
NTFY_PRIORITY: int = CONFIG.get("ntfy", {}).get("default_priority", 4)

# Twilio SMS alert settings (secrets from .env, flags from YAML)
TWILIO_ENABLED: bool = CONFIG.get("twilio", {}).get("enabled", False)
TWILIO_ACCOUNT_SID: str = os.getenv("TWILIO_ACCOUNT_SID") or CONFIG.get("twilio", {}).get("account_sid", "")
TWILIO_AUTH_TOKEN: str = os.getenv("TWILIO_AUTH_TOKEN") or CONFIG.get("twilio", {}).get("auth_token", "")
TWILIO_FROM: str = os.getenv("TWILIO_FROM_NUMBER") or CONFIG.get("twilio", {}).get("from_number", "")
TWILIO_TO: str = os.getenv("TWILIO_TO_NUMBER") or CONFIG.get("twilio", {}).get("to_number", "")

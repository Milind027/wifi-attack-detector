"""
Telegram Bot notifier for WiFi Attack Detector.
Sends attack alerts to a Telegram chat via the Bot API.
"""

import logging
import urllib.request
import urllib.parse
import urllib.error
import json


class TelegramNotifier:
    """Sends messages to a Telegram chat using the Bot HTTP API."""

    API_URL = "https://api.telegram.org/bot{token}/sendMessage"

    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.enabled = bool(bot_token and chat_id)
        if self.enabled:
            logging.info("TelegramNotifier initialized")
        else:
            logging.debug("TelegramNotifier disabled (no token/chat_id)")

    def send_message(self, text: str) -> bool:
        """
        Send a text message to the configured Telegram chat.
        Uses urllib so there are no extra dependencies (no `requests` needed).
        Returns True on success, False on failure.
        """
        if not self.enabled:
            logging.debug("Telegram alert skipped: not configured")
            return False

        url = self.API_URL.format(token=self.bot_token)
        payload = json.dumps({
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML"
        }).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )

        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status == 200:
                    logging.info(f"Telegram alert sent to chat {self.chat_id}")
                    return True
                else:
                    logging.warning(f"Telegram API returned status {resp.status}")
                    return False
        except urllib.error.URLError as e:
            logging.error(f"Telegram alert failed: {e}")
            return False
        except Exception as e:
            logging.error(f"Telegram alert error: {e}")
            return False

    def send_attack_alert(self, attack_type: str, severity: str,
                          src_mac: str, dst_mac: str, ssid: str,
                          details: str = "") -> bool:
        """Send a formatted attack alert to Telegram."""
        severity_emoji = {"high": "🔴", "medium": "🟠", "low": "🟢"}.get(severity, "⚪")
        text = (
            f"{severity_emoji} <b>WiFi Attack Detected</b>\n\n"
            f"<b>Type:</b> {attack_type}\n"
            f"<b>Severity:</b> {severity.upper()}\n"
            f"<b>Source:</b> <code>{src_mac}</code>\n"
            f"<b>Target:</b> <code>{dst_mac}</code>\n"
            f"<b>SSID:</b> {ssid}\n"
        )
        if details:
            text += f"\n<i>{details}</i>"
        return self.send_message(text)

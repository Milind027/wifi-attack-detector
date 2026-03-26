"""
Twilio SMS notifier for WiFi Attack Detector.
Sends attack alerts via SMS using the Twilio REST API.
Zero external dependencies — uses urllib with HTTP Basic Auth.
"""

import logging
import urllib.request
import urllib.parse
import urllib.error
import base64


class TwilioNotifier:
    """Sends SMS messages via the Twilio REST API."""

    API_URL = "https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"

    def __init__(self, account_sid: str, auth_token: str,
                 from_number: str, to_number: str):
        self.account_sid = account_sid
        self.auth_token = auth_token
        self.from_number = from_number
        self.to_number = to_number
        self.enabled = bool(account_sid and auth_token and from_number and to_number)

        if self.enabled:
            logging.info("TwilioNotifier initialized")
        else:
            logging.debug("TwilioNotifier disabled (missing credentials)")

    def send_sms(self, body: str) -> bool:
        """
        Send an SMS via Twilio REST API.
        Uses urllib with Basic Auth — no twilio SDK needed.
        """
        if not self.enabled:
            logging.debug("Twilio SMS skipped: not configured")
            return False

        # Truncate to SMS limit (1600 chars for Twilio)
        if len(body) > 1600:
            body = body[:1597] + "..."

        url = self.API_URL.format(sid=self.account_sid)
        data = urllib.parse.urlencode({
            "From": self.from_number,
            "To": self.to_number,
            "Body": body
        }).encode("utf-8")

        # HTTP Basic Auth: base64(account_sid:auth_token)
        credentials = base64.b64encode(
            f"{self.account_sid}:{self.auth_token}".encode()
        ).decode()

        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Authorization", f"Basic {credentials}")

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                if resp.status == 201:
                    logging.info(f"Twilio SMS sent to {self.to_number}")
                    return True
                else:
                    logging.warning(f"Twilio API returned status {resp.status}")
                    return False
        except urllib.error.HTTPError as e:
            logging.error(f"Twilio SMS failed ({e.code}): {e.read().decode()}")
            return False
        except Exception as e:
            logging.error(f"Twilio SMS error: {e}")
            return False

    def send_attack_alert(self, attack_type: str, severity: str,
                          src_mac: str, dst_mac: str, ssid: str,
                          details: str = "") -> bool:
        """Send a formatted attack alert via SMS."""
        severity_icon = {"high": "🔴", "medium": "🟠", "low": "🟢"}.get(severity, "⚪")
        body = (
            f"{severity_icon} WiFi Attack Detected\n"
            f"Type: {attack_type}\n"
            f"Severity: {severity.upper()}\n"
            f"Source: {src_mac}\n"
            f"Target: {dst_mac}\n"
            f"SSID: {ssid}"
        )
        if details:
            body += f"\n{details}"
        return self.send_sms(body)

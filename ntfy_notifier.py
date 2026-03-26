"""
ntfy.sh push notifier for WiFi Attack Detector.
Sends attack alerts as push notifications via ntfy.sh (no app install required).
"""

import logging
import urllib.request
import urllib.error


class NtfyNotifier:
    """Sends push notifications via ntfy.sh HTTP API."""

    # Map severity to ntfy priority levels
    SEVERITY_PRIORITY = {
        "high": 5,     # urgent
        "medium": 4,   # high
        "low": 3,      # default
    }

    SEVERITY_TAGS = {
        "high": "rotating_light,skull",
        "medium": "warning,eyes",
        "low": "information_source",
    }

    def __init__(self, topic: str, default_priority: int = 4):
        self.topic = topic.rstrip("/")
        self.default_priority = default_priority
        self.enabled = bool(topic)
        if self.enabled:
            logging.info(f"NtfyNotifier initialized for topic: {self.topic}")
        else:
            logging.debug("NtfyNotifier disabled (no topic)")

    def send_message(self, title: str, body: str,
                     priority: int = None, tags: str = "") -> bool:
        """
        Publish a notification to the ntfy topic.
        Uses plain HTTP POST — zero dependencies.
        """
        if not self.enabled:
            logging.debug("ntfy alert skipped: not configured")
            return False

        req = urllib.request.Request(
            self.topic,
            data=body.encode("utf-8"),
            method="POST"
        )
        req.add_header("Title", title)
        req.add_header("Priority", str(priority or self.default_priority))
        if tags:
            req.add_header("Tags", tags)

        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status == 200:
                    logging.info(f"ntfy alert sent: {title}")
                    return True
                else:
                    logging.warning(f"ntfy returned status {resp.status}")
                    return False
        except urllib.error.URLError as e:
            logging.error(f"ntfy alert failed: {e}")
            return False
        except Exception as e:
            logging.error(f"ntfy alert error: {e}")
            return False

    def send_attack_alert(self, attack_type: str, severity: str,
                          src_mac: str, dst_mac: str, ssid: str,
                          details: str = "") -> bool:
        """Send a formatted attack alert via ntfy."""
        priority = self.SEVERITY_PRIORITY.get(severity, self.default_priority)
        tags = self.SEVERITY_TAGS.get(severity, "")

        title = f"WiFi Attack: {attack_type} [{severity.upper()}]"
        body = (
            f"Type: {attack_type}\n"
            f"Severity: {severity.upper()}\n"
            f"Source: {src_mac}\n"
            f"Target: {dst_mac}\n"
            f"SSID: {ssid}\n"
        )
        if details:
            body += f"\n{details}"

        return self.send_message(title, body, priority=priority, tags=tags)

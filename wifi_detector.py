import os
import subprocess
import time
import logging
import collections
import threading
from logging.handlers import RotatingFileHandler
from dotenv import load_dotenv
from scapy.all import *
from PyQt5.QtCore import QThread, pyqtSignal
from database import Database
from notifier import WiFiNotifier
from telegram_notifier import TelegramNotifier
from ntfy_notifier import NtfyNotifier
from twilio_notifier import TwilioNotifier

# Load environment variables from .env file
load_dotenv()

# Configure logging with size-based rotation
from config import (PROJECT_DIR, LOG_PATH, LOG_LEVEL, LOG_MAX_BYTES, LOG_BACKUP_COUNT,
                    DEAUTH_THRESHOLD_COUNT, DEAUTH_THRESHOLD_WINDOW,
                    EVIL_TWIN_ENABLED, EVIL_TWIN_TRUSTED_APS,
                    PROBE_FLOOD_ENABLED, PROBE_FLOOD_COUNT, PROBE_FLOOD_WINDOW,
                    BEACON_FLOOD_ENABLED, BEACON_FLOOD_COUNT, BEACON_FLOOD_WINDOW,
                    PMKID_ENABLED, PMKID_COUNT, PMKID_WINDOW,
                    TELEGRAM_ENABLED, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
                    NTFY_ENABLED, NTFY_TOPIC, NTFY_PRIORITY,
                    TWILIO_ENABLED, TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN,
                    TWILIO_FROM, TWILIO_TO)
log_dir = PROJECT_DIR
log_path = LOG_PATH
os.makedirs(log_dir, exist_ok=True)
logger = logging.getLogger()
if not logger.handlers:
    logger.setLevel(getattr(logging, LOG_LEVEL, logging.DEBUG))
    handler = RotatingFileHandler(log_path, maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUP_COUNT)
    handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    logger.addHandler(handler)

# Official email credentials — loaded from .env
OFFICIAL_SENDER_EMAIL = os.getenv("SENDER_EMAIL")
OFFICIAL_SENDER_PASSWORD = os.getenv("SENDER_PASSWORD")

class SniffThread(QThread):
    """Background thread for packet sniffing and processing.
    
    Processes packets entirely in the background thread.
    Only emits lightweight signals for UI updates.
    """
    attack_signal = pyqtSignal(dict)    # emitted when attack detected
    ap_update_signal = pyqtSignal()     # emitted when nearby_aps changed

    def __init__(self, interface, detector=None):
        super().__init__()
        self.interface = interface
        self.detector = detector
        self.running = False
        logging.debug(f"Sniff-thread initialized for {interface}")

    def run(self):
        self.running = True
        logging.debug(f"Sniff thread running on {self.interface}")
        try:
            sniff(iface=self.interface, prn=self._process_packet, store=0,
                  stop_filter=lambda p: not self.running)
        except Exception as e:
            logging.error(f"Sniff error: {e}")

    def _process_packet(self, packet):
        """Process packet in background thread, emit signals for UI."""
        if not self.detector:
            return
        try:
            # Run ALL detection logic in this background thread
            attack_info = self.detector.packet_handler(packet)
            # Emit lightweight signals for UI refresh
            if attack_info:
                self.attack_signal.emit(attack_info)
            if packet.haslayer(Dot11Beacon):
                self.ap_update_signal.emit()
        except Exception as e:
            logging.error(f"Packet processing error: {e}")

    def stop(self):
        self.running = False
        self.wait()
        logging.debug(f"Sniff thread stopped for {self.interface}")

class WiFiDetector:
    def __init__(self, interface="wlan0", ui=None, username=None,
                 threshold_count: int = DEAUTH_THRESHOLD_COUNT,
                 threshold_window: int = DEAUTH_THRESHOLD_WINDOW):
        self.base_interface = interface
        self.interface = f"{interface}mon"
        self.attacks = []
        self.ssid_map = {}
        self.nearby_aps = {}  # {bssid: {ssid, channel, signal, last_seen, encryption}}
        self.ui = ui
        self.username = username
        self.db = Database()

        # Threshold settings: N packets in X seconds triggers alert
        self.threshold_count = threshold_count
        self.threshold_window = threshold_window
        # Sliding window: {src_mac: deque of timestamps}
        self.deauth_timestamps: dict[str, collections.deque] = {}
        # Track which MACs already triggered an alert in the current window
        self.alerted_macs: dict[str, float] = {}

        # Detect host machine's MAC address for targeted attack detection
        self.host_mac: str = self._get_host_mac(interface)

        # Evil Twin detection: {ssid: set(bssid)}
        self.evil_twin_enabled: bool = EVIL_TWIN_ENABLED
        self.known_aps: dict[str, set[str]] = {}
        self._load_trusted_aps()

        # Probe request flood detection
        self.probe_flood_enabled: bool = PROBE_FLOOD_ENABLED
        self.probe_flood_count: int = PROBE_FLOOD_COUNT
        self.probe_flood_window: int = PROBE_FLOOD_WINDOW
        self.probe_timestamps: dict[str, collections.deque] = {}
        self.probe_alerted_macs: dict[str, float] = {}

        # Beacon flood detection
        self.beacon_flood_enabled: bool = BEACON_FLOOD_ENABLED
        self.beacon_flood_count: int = BEACON_FLOOD_COUNT
        self.beacon_flood_window: int = BEACON_FLOOD_WINDOW
        self.beacon_timestamps: dict[str, collections.deque] = {}
        self.beacon_alerted_macs: dict[str, float] = {}

        # PMKID attack detection (EAPOL key message flood)
        self.pmkid_enabled: bool = PMKID_ENABLED
        self.pmkid_count: int = PMKID_COUNT
        self.pmkid_window: int = PMKID_WINDOW
        self.eapol_timestamps: dict[str, collections.deque] = {}
        self.eapol_alerted_macs: dict[str, float] = {}

        smtp_config = {'host': 'smtp.gmail.com', 'port': 587}
        receiver_email = self.db.get_email_config(self.username)[3] if self.username and self.db.get_email_config(self.username) else None
        logging.debug(f"Receiver email for {self.username}: {receiver_email}")
        self.notifier = WiFiNotifier(smtp_config, OFFICIAL_SENDER_EMAIL, OFFICIAL_SENDER_PASSWORD, receiver_email)
        self.sniff_thread = SniffThread(self.interface, detector=self)

        # Telegram notifier
        if TELEGRAM_ENABLED:
            self.telegram = TelegramNotifier(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)
        else:
            self.telegram = TelegramNotifier("", "")

        # ntfy.sh notifier
        if NTFY_ENABLED:
            self.ntfy = NtfyNotifier(NTFY_TOPIC, NTFY_PRIORITY)
        else:
            self.ntfy = NtfyNotifier("", NTFY_PRIORITY)

        # Twilio SMS notifier
        if TWILIO_ENABLED:
            self.twilio = TwilioNotifier(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN,
                                         TWILIO_FROM, TWILIO_TO)
        else:
            self.twilio = TwilioNotifier("", "", "", "")

        self.ensure_monitor_mode()
        if receiver_email:
            logging.debug("Sending test email on initialization")
            self.notifier.send_email("WiFi Detector Test", "Test email on initialization")
        else:
            logging.warning("Skipping test email: No receiver email set")
        logging.debug(f"WiFiDetector initialized for {interface}, user: {username}, "
                      f"threshold: {self.threshold_count} packets / {self.threshold_window}s")

    def set_threshold(self, count: int, window: int) -> None:
        """Update the deauth alert threshold at runtime."""
        self.threshold_count = count
        self.threshold_window = window
        logging.info(f"Threshold updated: {count} packets / {window}s")

    def _get_host_mac(self, interface: str) -> str:
        """Get the MAC address of the host wireless interface."""
        try:
            result = subprocess.run(
                ["cat", f"/sys/class/net/{interface}/address"],
                capture_output=True, text=True
            )
            mac = result.stdout.strip().lower()
            if mac:
                logging.debug(f"Host MAC for {interface}: {mac}")
                return mac
        except Exception as e:
            logging.warning(f"Could not get host MAC: {e}")
        return ""

    def _classify_deauth(self, dst_mac: str) -> tuple[str, str]:
        """
        Classify a deauth attack based on destination MAC.
        Returns (attack_type, severity).
        """
        BROADCAST_MAC = "ff:ff:ff:ff:ff:ff"
        dst_lower = dst_mac.lower() if dst_mac else ""

        if dst_lower == BROADCAST_MAC:
            return "deauth_broadcast", "medium"
        elif self.host_mac and dst_lower == self.host_mac:
            return "deauth_targeted", "high"
        else:
            return "deauth_targeted", "medium"

    def _load_trusted_aps(self) -> None:
        """Pre-load trusted APs from config into known_aps."""
        for ap in EVIL_TWIN_TRUSTED_APS:
            ssid = ap.get("ssid", "")
            bssid = ap.get("bssid", "").lower()
            if ssid and bssid:
                if ssid not in self.known_aps:
                    self.known_aps[ssid] = set()
                self.known_aps[ssid].add(bssid)
        if self.known_aps:
            logging.info(f"Loaded {len(self.known_aps)} trusted AP SSIDs from config")

    def _check_evil_twin(self, ssid: str, bssid: str) -> bool:
        """
        Check if a beacon is a potential Evil Twin.
        Returns True if the SSID was already seen with different BSSID(s)
        and this BSSID is new (possible rogue AP).
        """
        if not self.evil_twin_enabled or not ssid or ssid == "Hidden":
            return False

        bssid_lower = bssid.lower()

        if ssid in self.known_aps:
            if bssid_lower not in self.known_aps[ssid]:
                # New BSSID for a known SSID → potential Evil Twin!
                self.known_aps[ssid].add(bssid_lower)
                return True
        else:
            # First time seeing this SSID — auto-learn it
            self.known_aps[ssid] = {bssid_lower}

        return False

    def _check_probe_flood(self, src_mac: str) -> bool:
        """
        Sliding window probe flood check.
        Returns True if the probe count threshold was just crossed.
        """
        now = time.time()

        if src_mac not in self.probe_timestamps:
            self.probe_timestamps[src_mac] = collections.deque()

        window = self.probe_timestamps[src_mac]
        window.append(now)

        cutoff = now - self.probe_flood_window
        while window and window[0] < cutoff:
            window.popleft()

        if src_mac in self.probe_alerted_macs and (now - self.probe_alerted_macs[src_mac]) > self.probe_flood_window:
            del self.probe_alerted_macs[src_mac]

        if len(window) >= self.probe_flood_count and src_mac not in self.probe_alerted_macs:
            self.probe_alerted_macs[src_mac] = now
            return True

        return False

    def _check_beacon_flood(self, bssid: str) -> bool:
        """
        Sliding window beacon flood check.
        Returns True if the beacon count threshold was just crossed for this BSSID.
        """
        now = time.time()

        if bssid not in self.beacon_timestamps:
            self.beacon_timestamps[bssid] = collections.deque()

        window = self.beacon_timestamps[bssid]
        window.append(now)

        cutoff = now - self.beacon_flood_window
        while window and window[0] < cutoff:
            window.popleft()

        if bssid in self.beacon_alerted_macs and (now - self.beacon_alerted_macs[bssid]) > self.beacon_flood_window:
            del self.beacon_alerted_macs[bssid]

        if len(window) >= self.beacon_flood_count and bssid not in self.beacon_alerted_macs:
            self.beacon_alerted_macs[bssid] = now
            return True

        return False

    def _check_pmkid(self, src_mac: str) -> bool:
        """
        Sliding window EAPOL/PMKID flood check.
        Returns True if the EAPOL key count threshold was just crossed.
        """
        now = time.time()

        if src_mac not in self.eapol_timestamps:
            self.eapol_timestamps[src_mac] = collections.deque()

        window = self.eapol_timestamps[src_mac]
        window.append(now)

        cutoff = now - self.pmkid_window
        while window and window[0] < cutoff:
            window.popleft()

        if src_mac in self.eapol_alerted_macs and (now - self.eapol_alerted_macs[src_mac]) > self.pmkid_window:
            del self.eapol_alerted_macs[src_mac]

        if len(window) >= self.pmkid_count and src_mac not in self.eapol_alerted_macs:
            self.eapol_alerted_macs[src_mac] = now
            return True

        return False

    def _check_threshold(self, src_mac: str) -> bool:
        """
        Sliding window threshold check.
        Returns True if the threshold was just crossed (first time in this window).
        """
        now = time.time()

        # Initialize deque for this MAC if not seen before
        if src_mac not in self.deauth_timestamps:
            self.deauth_timestamps[src_mac] = collections.deque()

        window = self.deauth_timestamps[src_mac]
        window.append(now)

        # Remove timestamps outside the window
        cutoff = now - self.threshold_window
        while window and window[0] < cutoff:
            window.popleft()

        # Clear alert flag if we haven't seen this MAC for a full window
        if src_mac in self.alerted_macs and (now - self.alerted_macs[src_mac]) > self.threshold_window:
            del self.alerted_macs[src_mac]

        # Check if threshold crossed and not already alerted
        if len(window) >= self.threshold_count and src_mac not in self.alerted_macs:
            self.alerted_macs[src_mac] = now
            return True

        return False

    def get_available_interfaces(self):
        result = subprocess.run(["iwconfig"], capture_output=True, text=True).stdout
        interfaces = [line.split()[0] for line in result.splitlines() if "IEEE 802.11" in line]
        logging.debug(f"Available interfaces: {interfaces}")
        return interfaces

    def set_interface(self, interface):
        self.stop_monitoring()
        self.base_interface = interface
        self.interface = f"{interface}mon"
        self.sniff_thread.interface = self.interface
        self.ensure_monitor_mode()
        logging.info(f"Interface set to {interface}")

    def check_monitor_mode(self):
        result = subprocess.run(["iwconfig"], capture_output=True, text=True).stdout
        logging.debug(f"iwconfig output: {result}")
        return f"{self.base_interface}mon" in result and "Mode:Monitor" in result

    def enable_monitor_mode(self):
        logging.info("Enabling monitor mode...")
        interfaces = subprocess.run(["iwconfig"], capture_output=True, text=True).stdout
        if self.base_interface not in interfaces:
            logging.error(f"Interface {self.base_interface} not found")
            raise RuntimeError("No wireless interface found.")
        
        result = subprocess.run(["airmon-ng", "start", self.base_interface], 
                              capture_output=True, text=True)
        logging.debug(result.stdout)
        if result.returncode != 0:
            logging.error(f"airmon-ng failed: {result.stderr}")
            raise RuntimeError("Failed to enable monitor mode.")
        
        subprocess.run(["iwconfig", self.interface, "channel", "1"], check=True)
        subprocess.run(["ifconfig", self.interface, "up"], check=True)
        self.sniff_thread.interface = self.interface
        time.sleep(2)
        logging.debug(f"Interface updated to: {self.interface}")

    def ensure_monitor_mode(self):
        if not self.check_monitor_mode():
            self.enable_monitor_mode()

    def send_notification(self, title, message):
        try:
            subprocess.Popen(
                ["notify-send", "-i", "dialog-warning", title, message],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
        except Exception:
            pass
        logging.debug(f"Sent desktop notification: {message}")

    def packet_handler(self, packet):
        """Process a packet. Returns attack dict if attack detected, else None."""
        logging.debug(f"Packet received: {packet.summary()}")
        if packet.haslayer(Dot11Beacon):
            bssid = packet.addr2
            ssid = packet.info.decode() if packet.info else "Hidden"
            self.ssid_map[bssid] = ssid

            # Extract channel and signal for network map
            channel = 0
            elt = packet.getlayer(Dot11Elt)
            while elt:
                if elt.ID == 3 and elt.info:  # DS Parameter Set = channel
                    channel = elt.info[0]
                    break
                elt = elt.payload.getlayer(Dot11Elt)
            signal = packet.dBm_AntSignal if hasattr(packet, 'dBm_AntSignal') else -100

            # Detect encryption type
            cap = packet.sprintf("{Dot11Beacon:%Dot11Beacon.cap%}").strip()
            if "privacy" in cap:
                encryption = "WPA/WPA2"
            else:
                encryption = "Open"

            self.nearby_aps[bssid] = {
                "ssid": ssid,
                "channel": channel,
                "signal": signal,
                "last_seen": time.strftime('%H:%M:%S', time.localtime()),
                "encryption": encryption
            }

            logging.debug(f"AP tracked: {bssid} / '{ssid}' ch={channel} sig={signal}")

            # Evil Twin detection
            if self._check_evil_twin(ssid, bssid):
                timestamp = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
                known_bssids = self.known_aps.get(ssid, set()) - {bssid.lower()}
                attack = {
                    "timestamp": timestamp,
                    "src_mac": bssid,
                    "dst_mac": "N/A",
                    "ssid": ssid,
                    "attack_type": "evil_twin",
                    "severity": "high"
                }
                self.db.log_attack(attack)
                self.attacks.append(attack)
                log_msg = (f"Evil Twin detected! SSID '{ssid}' has new BSSID {bssid}. "
                           f"Known BSSIDs: {known_bssids}")
                logging.warning(log_msg)
                self.send_notification("Evil Twin Detected", f"[HIGH] '{ssid}' from {bssid}")
                self._send_alerts_async(
                    "Evil Twin / Rogue AP Alert [HIGH]",
                    f"SSID: {ssid}\nNew BSSID: {bssid}\n"
                    f"Known legitimate BSSIDs: {known_bssids}\n"
                    f"This may be a rogue access point impersonating your network!",
                    "evil_twin", "high", bssid, "N/A", ssid,
                    f"New BSSID detected. Known: {known_bssids}"
                )
                return attack

            # Beacon flood detection
            if self.beacon_flood_enabled and self._check_beacon_flood(bssid):
                timestamp = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
                attack = {
                    "timestamp": timestamp,
                    "src_mac": bssid,
                    "dst_mac": "N/A",
                    "ssid": ssid,
                    "attack_type": "beacon_flood",
                    "severity": "medium"
                }
                self.db.log_attack(attack)
                self.attacks.append(attack)
                log_msg = f"Beacon flood from {bssid} / '{ssid}' ({self.beacon_flood_count} beacons in {self.beacon_flood_window}s)"
                logging.warning(log_msg)
                self.send_notification("Beacon Flood Detected", f"[MEDIUM] {bssid} ('{ssid}')")
                self._send_alerts_async(
                    "Beacon Flood Alert [MEDIUM]",
                    f"BSSID: {bssid}\nSSID: {ssid}\n{log_msg}",
                    "beacon_flood", "medium", bssid, "N/A", ssid, log_msg
                )
                return attack
        elif packet.haslayer(Dot11Deauth):
            src = packet.addr2
            dst = packet.addr1
            ssid = self.ssid_map.get(src, "Unknown")
            timestamp = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())

            # Classify attack: broadcast vs targeted
            attack_type, severity = self._classify_deauth(dst)

            attack = {
                "timestamp": timestamp,
                "src_mac": src,
                "dst_mac": dst,
                "ssid": ssid,
                "attack_type": attack_type,
                "severity": severity
            }

            # Always log to database (forensic record)
            self.db.log_attack(attack)
            self.attacks.append(attack)

            # Only alert if threshold is crossed
            if self._check_threshold(src):
                log_msg = f"{timestamp} | {attack_type} ({severity}) | {src} | {dst} | {ssid}"
                logging.info(f"Deauth ALERT (threshold crossed): {log_msg}")
                self.send_notification(f"{attack_type.replace('_', ' ').title()} Detected", f"[{severity.upper()}] {src} -> {dst}")
                self._send_alerts_async(
                    f"WiFi Deauth Attack Alert [{severity.upper()}]",
                    f"Type: {attack_type}\nSeverity: {severity}\n"
                    f"Threshold crossed: {self.threshold_count} packets in {self.threshold_window}s\n{log_msg}",
                    attack_type, severity, src, dst, ssid,
                    f"Threshold: {self.threshold_count} packets in {self.threshold_window}s"
                )
                return attack
            else:
                logging.debug(f"Deauth packet logged (below threshold): {attack_type} {src} -> {dst}")
                return attack

        elif packet.haslayer(Dot11ProbeReq) and self.probe_flood_enabled:
            src = packet.addr2
            if src and self._check_probe_flood(src):
                timestamp = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
                ssid_requested = packet.info.decode() if packet.info else "Broadcast"
                attack = {
                    "timestamp": timestamp,
                    "src_mac": src,
                    "dst_mac": "N/A",
                    "ssid": ssid_requested,
                    "attack_type": "probe_flood",
                    "severity": "medium"
                }
                self.db.log_attack(attack)
                self.attacks.append(attack)
                log_msg = f"Probe flood from {src} ({self.probe_flood_count} probes in {self.probe_flood_window}s)"
                logging.warning(log_msg)
                self.send_notification("Probe Flood Detected", f"[MEDIUM] {src}")
                self._send_alerts_async(
                    "Probe Request Flood Alert [MEDIUM]",
                    f"Source: {src}\nSSID requested: {ssid_requested}\n{log_msg}",
                    "probe_flood", "medium", src, "N/A", ssid_requested, log_msg
                )
                return attack

        elif packet.haslayer(EAPOL) and self.pmkid_enabled:
            src = packet.addr2
            dst = packet.addr1
            if src and self._check_pmkid(src):
                timestamp = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
                ssid = self.ssid_map.get(src, "Unknown")
                attack = {
                    "timestamp": timestamp,
                    "src_mac": src,
                    "dst_mac": dst or "N/A",
                    "ssid": ssid,
                    "attack_type": "pmkid",
                    "severity": "high"
                }
                self.db.log_attack(attack)
                self.attacks.append(attack)
                log_msg = f"PMKID attack from {src} ({self.pmkid_count} EAPOL messages in {self.pmkid_window}s)"
                logging.warning(log_msg)
                self.send_notification("PMKID Attack Detected", f"[HIGH] {src}")
                self._send_alerts_async(
                    "PMKID Attack Alert [HIGH]",
                    f"Source: {src}\nTarget: {dst}\nSSID: {ssid}\n{log_msg}\n"
                    f"An attacker may be harvesting PMKID hashes for offline cracking!",
                    "pmkid", "high", src, dst or "N/A", ssid,
                    f"PMKID hash harvesting detected! {log_msg}"
                )
                return attack
        return None

    def _send_alerts_async(self, email_subject, email_body,
                           attack_type, severity, src, dst, ssid, detail):
        """Send all notifications in a background thread to avoid blocking the GUI."""
        def _worker():
            try:
                if self.notifier.receiver_email:
                    self.notifier.send_email(email_subject, email_body)
            except Exception as e:
                logging.error(f"Email alert failed: {e}")
            try:
                self.telegram.send_attack_alert(attack_type, severity, src, dst, ssid, detail)
            except Exception as e:
                logging.error(f"Telegram alert failed: {e}")
            try:
                self.ntfy.send_attack_alert(attack_type, severity, src, dst, ssid, detail)
            except Exception as e:
                logging.error(f"ntfy alert failed: {e}")
            try:
                self.twilio.send_attack_alert(attack_type, severity, src, dst, ssid, detail)
            except Exception as e:
                logging.error(f"Twilio alert failed: {e}")

        t = threading.Thread(target=_worker, daemon=True)
        t.start()

    def start_monitoring(self):
        logging.info(f"Starting WiFi monitoring on {self.interface}")
        self.ensure_monitor_mode()
        self.sniff_thread.start()

    def stop_monitoring(self):
        self.sniff_thread.stop()
        logging.info("Monitoring stopped")


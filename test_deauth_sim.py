#!/usr/bin/env python3
"""
Fake Deauth Attack Simulator — FOR TESTING ONLY
Sends simulated deauth packets on your monitor mode interface
to verify that WiFi Attack Detector is working correctly.

Usage:
    sudo venv/bin/python test_deauth_sim.py

WARNING: Only use this on YOUR OWN network for testing.
"""

from scapy.all import Dot11, Dot11Deauth, RadioTap, sendp
import time
import sys

# ── Config ────────────────────────────────────
INTERFACE = "wlan0mon"           # Your monitor mode interface
FAKE_AP_MAC = "AA:BB:CC:DD:EE:FF"  # Fake attacker MAC
TARGET_MAC = "ff:ff:ff:ff:ff:ff"   # Broadcast (flood)
PACKET_COUNT = 15                  # Packets to send (above default threshold of 10)
DELAY = 0.2                        # Seconds between packets
# ──────────────────────────────────────────────

def main():
    print("=" * 50)
    print("🧪 Deauth Attack Simulator (TESTING ONLY)")
    print("=" * 50)
    print(f"  Interface : {INTERFACE}")
    print(f"  Attacker  : {FAKE_AP_MAC}")
    print(f"  Target    : {TARGET_MAC}")
    print(f"  Packets   : {PACKET_COUNT}")
    print(f"  Delay     : {DELAY}s")
    print("=" * 50)

    # Build the deauth frame
    packet = RadioTap() / Dot11(
        type=0,        # Management frame
        subtype=12,    # Deauthentication
        addr1=TARGET_MAC,       # Destination
        addr2=FAKE_AP_MAC,      # Source (attacker)
        addr3=FAKE_AP_MAC       # BSSID
    ) / Dot11Deauth(reason=7)   # Reason: Class 3 frame from non-associated station

    print(f"\n🚀 Sending {PACKET_COUNT} deauth packets...\n")

    for i in range(PACKET_COUNT):
        sendp(packet, iface=INTERFACE, verbose=False)
        print(f"  [{i+1}/{PACKET_COUNT}] Deauth sent → {TARGET_MAC}")
        time.sleep(DELAY)

    print(f"\n✅ Done! Sent {PACKET_COUNT} deauth packets.")
    print("📡 Check your WiFi Attack Detector — it should have triggered an alert!")

if __name__ == "__main__":
    if "linux" not in sys.platform:
        print("❌ This script only works on Linux with monitor mode.")
        sys.exit(1)
    main()

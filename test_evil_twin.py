"""
Unit tests for Evil Twin / Rogue AP detection logic.
Tests the _check_evil_twin method in isolation.
"""

import unittest


class EvilTwinChecker:
    """
    Standalone Evil Twin detection logic extracted from WiFiDetector.
    """

    def __init__(self, enabled: bool = True, trusted_aps: list = None):
        self.evil_twin_enabled = enabled
        self.known_aps: dict[str, set[str]] = {}
        if trusted_aps:
            for ap in trusted_aps:
                ssid = ap.get("ssid", "")
                bssid = ap.get("bssid", "").lower()
                if ssid and bssid:
                    if ssid not in self.known_aps:
                        self.known_aps[ssid] = set()
                    self.known_aps[ssid].add(bssid)

    def check_evil_twin(self, ssid: str, bssid: str) -> bool:
        if not self.evil_twin_enabled or not ssid or ssid == "Hidden":
            return False
        bssid_lower = bssid.lower()
        if ssid in self.known_aps:
            if bssid_lower not in self.known_aps[ssid]:
                self.known_aps[ssid].add(bssid_lower)
                return True
        else:
            self.known_aps[ssid] = {bssid_lower}
        return False


class TestEvilTwinDetection(unittest.TestCase):

    def test_first_ap_auto_learned(self):
        """First AP for an SSID should be auto-learned, not flagged."""
        checker = EvilTwinChecker()
        result = checker.check_evil_twin("HomeWiFi", "AA:BB:CC:DD:EE:FF")
        self.assertFalse(result, "First AP should be auto-learned, not flagged")
        self.assertIn("HomeWiFi", checker.known_aps)

    def test_same_bssid_no_alert(self):
        """Same BSSID seen again should NOT trigger alert."""
        checker = EvilTwinChecker()
        checker.check_evil_twin("HomeWiFi", "AA:BB:CC:DD:EE:FF")
        result = checker.check_evil_twin("HomeWiFi", "AA:BB:CC:DD:EE:FF")
        self.assertFalse(result, "Same BSSID should not alert")

    def test_new_bssid_triggers_evil_twin(self):
        """New BSSID for known SSID should trigger Evil Twin alert."""
        checker = EvilTwinChecker()
        checker.check_evil_twin("HomeWiFi", "AA:BB:CC:DD:EE:FF")
        result = checker.check_evil_twin("HomeWiFi", "11:22:33:44:55:66")
        self.assertTrue(result, "New BSSID for known SSID = Evil Twin")

    def test_different_ssids_independent(self):
        """Different SSIDs should be tracked independently."""
        checker = EvilTwinChecker()
        checker.check_evil_twin("HomeWiFi", "AA:BB:CC:DD:EE:FF")
        result = checker.check_evil_twin("OfficeWiFi", "11:22:33:44:55:66")
        self.assertFalse(result, "Different SSID = new AP, not Evil Twin")

    def test_trusted_ap_pre_loaded(self):
        """Trusted APs from config should be pre-loaded."""
        trusted = [{"ssid": "HomeWiFi", "bssid": "AA:BB:CC:DD:EE:FF"}]
        checker = EvilTwinChecker(trusted_aps=trusted)
        # Same BSSID as trusted — no alert
        result = checker.check_evil_twin("HomeWiFi", "AA:BB:CC:DD:EE:FF")
        self.assertFalse(result)
        # New BSSID — Evil Twin alert
        result = checker.check_evil_twin("HomeWiFi", "11:22:33:44:55:66")
        self.assertTrue(result)

    def test_disabled_no_detection(self):
        """When disabled, no Evil Twin detection should occur."""
        checker = EvilTwinChecker(enabled=False)
        checker.check_evil_twin("HomeWiFi", "AA:BB:CC:DD:EE:FF")
        result = checker.check_evil_twin("HomeWiFi", "11:22:33:44:55:66")
        self.assertFalse(result, "No detection when disabled")

    def test_hidden_ssid_ignored(self):
        """Hidden SSIDs should be ignored."""
        checker = EvilTwinChecker()
        result = checker.check_evil_twin("Hidden", "AA:BB:CC:DD:EE:FF")
        self.assertFalse(result, "Hidden SSIDs should be skipped")

    def test_case_insensitive_bssid(self):
        """BSSID comparison should be case-insensitive."""
        checker = EvilTwinChecker()
        checker.check_evil_twin("HomeWiFi", "AA:BB:CC:DD:EE:FF")
        result = checker.check_evil_twin("HomeWiFi", "aa:bb:cc:dd:ee:ff")
        self.assertFalse(result, "BSSID comparison should be case-insensitive")

    def test_no_duplicate_alert_same_rogue(self):
        """Rogue AP seen again should NOT re-trigger alert."""
        checker = EvilTwinChecker()
        checker.check_evil_twin("HomeWiFi", "AA:BB:CC:DD:EE:FF")
        checker.check_evil_twin("HomeWiFi", "11:22:33:44:55:66")  # first alert
        result = checker.check_evil_twin("HomeWiFi", "11:22:33:44:55:66")  # same rogue
        self.assertFalse(result, "Same rogue BSSID should not re-alert")


if __name__ == "__main__":
    unittest.main()

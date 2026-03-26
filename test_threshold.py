"""
Unit tests for the deauth threshold sliding window logic.
Tests the _check_threshold method of WiFiDetector in isolation,
without requiring Scapy, PyQt5, or any network hardware.
"""

import time
import collections
import unittest


class ThresholdChecker:
    """
    Standalone version of the threshold logic from WiFiDetector,
    extracted for unit testing without hardware/GUI dependencies.
    """

    def __init__(self, threshold_count: int = 10, threshold_window: int = 5):
        self.threshold_count = threshold_count
        self.threshold_window = threshold_window
        self.deauth_timestamps: dict[str, collections.deque] = {}
        self.alerted_macs: dict[str, float] = {}

    def set_threshold(self, count: int, window: int) -> None:
        self.threshold_count = count
        self.threshold_window = window

    def check_threshold(self, src_mac: str, timestamp: float = None) -> bool:
        """Check if threshold is crossed. Accepts optional timestamp for testing."""
        now = timestamp if timestamp is not None else time.time()

        if src_mac not in self.deauth_timestamps:
            self.deauth_timestamps[src_mac] = collections.deque()

        window = self.deauth_timestamps[src_mac]
        window.append(now)

        cutoff = now - self.threshold_window
        while window and window[0] < cutoff:
            window.popleft()

        if src_mac in self.alerted_macs and (now - self.alerted_macs[src_mac]) > self.threshold_window:
            del self.alerted_macs[src_mac]

        if len(window) >= self.threshold_count and src_mac not in self.alerted_macs:
            self.alerted_macs[src_mac] = now
            return True

        return False


class TestDeauthThreshold(unittest.TestCase):
    """Tests for the sliding window deauth threshold system."""

    def test_below_threshold_no_alert(self):
        """9 packets in 5 seconds should NOT trigger alert (threshold=10)."""
        checker = ThresholdChecker(threshold_count=10, threshold_window=5)
        base_time = 1000.0
        for i in range(9):
            result = checker.check_threshold("AA:BB:CC:DD:EE:FF", base_time + i * 0.5)
        self.assertFalse(result, "Should not alert below threshold")

    def test_at_threshold_triggers_alert(self):
        """Exactly 10 packets in 5 seconds SHOULD trigger alert."""
        checker = ThresholdChecker(threshold_count=10, threshold_window=5)
        base_time = 1000.0
        results = []
        for i in range(10):
            results.append(checker.check_threshold("AA:BB:CC:DD:EE:FF", base_time + i * 0.4))
        self.assertTrue(results[-1], "Should alert at threshold")
        self.assertFalse(any(results[:-1]), "Should not alert before reaching threshold")

    def test_no_duplicate_alert_in_same_window(self):
        """After threshold crossed, additional packets should NOT re-trigger."""
        checker = ThresholdChecker(threshold_count=3, threshold_window=5)
        base_time = 1000.0
        # Trigger threshold
        for i in range(3):
            checker.check_threshold("AA:BB:CC:DD:EE:FF", base_time + i)
        # Additional packets in same window
        result = checker.check_threshold("AA:BB:CC:DD:EE:FF", base_time + 3)
        self.assertFalse(result, "Should not re-alert in same window")

    def test_alert_resets_after_window_expires(self):
        """After a full window passes, a new burst should trigger again."""
        checker = ThresholdChecker(threshold_count=3, threshold_window=5)
        base_time = 1000.0
        # First burst
        for i in range(3):
            checker.check_threshold("AA:BB:CC:DD:EE:FF", base_time + i)
        # Wait for window to expire
        new_base = base_time + 10  # well past the 5s window
        results = []
        for i in range(3):
            results.append(checker.check_threshold("AA:BB:CC:DD:EE:FF", new_base + i))
        self.assertTrue(results[-1], "Should re-alert after window resets")

    def test_different_macs_tracked_independently(self):
        """Each source MAC should have its own counter."""
        checker = ThresholdChecker(threshold_count=3, threshold_window=5)
        base_time = 1000.0
        # MAC1: 2 packets (below threshold)
        for i in range(2):
            checker.check_threshold("11:11:11:11:11:11", base_time + i)
        # MAC2: 3 packets (at threshold)
        results = []
        for i in range(3):
            results.append(checker.check_threshold("22:22:22:22:22:22", base_time + i))
        self.assertTrue(results[-1], "MAC2 should trigger independently")

    def test_packets_outside_window_are_pruned(self):
        """Old packets should be removed and not count toward threshold."""
        checker = ThresholdChecker(threshold_count=5, threshold_window=3)
        # Send 3 packets at t=0, 1, 2
        for i in range(3):
            checker.check_threshold("AA:BB:CC:DD:EE:FF", float(i))
        # Send 2 more at t=10, 11 (old ones should be pruned)
        r1 = checker.check_threshold("AA:BB:CC:DD:EE:FF", 10.0)
        r2 = checker.check_threshold("AA:BB:CC:DD:EE:FF", 11.0)
        self.assertFalse(r1, "Should not alert — old packets pruned")
        self.assertFalse(r2, "Should not alert — only 2 in window")

    def test_set_threshold_runtime_change(self):
        """Changing threshold at runtime should take effect immediately."""
        checker = ThresholdChecker(threshold_count=10, threshold_window=5)
        base_time = 1000.0
        # Send 3 packets — should not trigger with threshold=10
        for i in range(3):
            checker.check_threshold("AA:BB:CC:DD:EE:FF", base_time + i * 0.1)
        # Lower threshold to 3
        checker.set_threshold(3, 5)
        # The 3 packets are already in the window — next check should NOT re-trigger
        # because we need a new packet to evaluate
        result = checker.check_threshold("AA:BB:CC:DD:EE:FF", base_time + 0.5)
        self.assertTrue(result, "Should trigger after threshold lowered")


if __name__ == "__main__":
    unittest.main()

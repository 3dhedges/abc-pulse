"""The rolling error-rate window behind /api/health."""

import unittest
from unittest import mock

import support  # noqa: F401
import health_monitor
from health_monitor import ErrorRateMonitor


class ErrorRateMonitorTest(unittest.TestCase):
    def test_counts_and_rate(self):
        m = ErrorRateMonitor(window_seconds=60)
        for _ in range(9):
            m.record(ok=True)
        m.record(ok=False)
        self.assertEqual(m.snapshot(), {"requests": 10, "errors": 1, "errorRate": 0.1, "windowSeconds": 60})

    def test_empty_window_has_zero_rate(self):
        self.assertEqual(ErrorRateMonitor().snapshot()["errorRate"], 0.0)

    def test_old_events_drop_out_of_the_window(self):
        clock = [1000.0]
        with mock.patch.object(health_monitor.time, "monotonic", lambda: clock[0]):
            m = ErrorRateMonitor(window_seconds=60)
            m.record(ok=False)
            clock[0] += 61
            m.record(ok=True)
            self.assertEqual(m.snapshot()["errors"], 0)
            self.assertEqual(m.snapshot()["requests"], 1)


if __name__ == "__main__":
    unittest.main()

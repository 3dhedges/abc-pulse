"""Rolling error-rate monitor for health-score calculations.

Every call to /api/accounts/<id>/health records success or failure here.
/api/health reports the error rate over the last WINDOW_SECONDS. That's the
kind of signal an APM tool (Datadog, New Relic, ...) would alert on, and
scripts/watchdog.py plays that role in this demo.
"""

import threading
import time
from collections import deque

WINDOW_SECONDS = 60


class ErrorRateMonitor:
    """Thread-safe count of recent successes and failures in a sliding time window."""

    def __init__(self, window_seconds=WINDOW_SECONDS):
        self.window_seconds = window_seconds
        self._events = deque()  # (timestamp, ok) pairs, oldest first
        self._lock = threading.Lock()  # Flask serves requests on multiple threads

    def record(self, ok):
        """Record one calculation result."""
        with self._lock:
            self._events.append((time.monotonic(), ok))
            self._prune()

    def snapshot(self):
        """Return request and error counts plus the error rate for the current window."""
        with self._lock:
            self._prune()
            requests = len(self._events)
            errors = sum(1 for _, ok in self._events if not ok)
        return {
            "requests": requests,
            "errors": errors,
            "errorRate": round(errors / requests, 4) if requests else 0.0,
            "windowSeconds": self.window_seconds,
        }

    def _prune(self):
        """Drop events older than the window. Caller must hold the lock."""
        cutoff = time.monotonic() - self.window_seconds
        while self._events and self._events[0][0] < cutoff:
            self._events.popleft()

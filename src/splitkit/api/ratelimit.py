"""In-process fixed-window rate limiter, keyed by client.

Good enough for a single instance; a multi-instance deploy should move this to
the load balancer or a shared store (Redis), since each process counts alone.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable


class FixedWindowLimiter:
    def __init__(self, limit: int, window_s: float = 60.0, clock: Callable[[], float] = time.monotonic):
        self._limit = limit
        self._window_s = window_s
        self._clock = clock
        self._lock = threading.Lock()
        self._window = -1
        self._counts: dict[str, int] = {}

    def allow(self, client: str) -> bool:
        if self._limit <= 0:
            return True
        window = int(self._clock() // self._window_s)
        with self._lock:
            if window != self._window:
                # new window: every old counter is stale, so drop them all at once
                self._window = window
                self._counts = {}
            count = self._counts.get(client, 0)
            if count >= self._limit:
                return False
            self._counts[client] = count + 1
            return True

    def tracked_clients(self) -> int:
        with self._lock:
            return len(self._counts)

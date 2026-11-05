"""Einfacher, threadsicherer In-Memory-Rate-Limiter für Fehlversuche."""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable


class FailureRateLimiter:
    """Sperrt einen Schlüssel für ``lockout_seconds``, sobald innerhalb von
    ``window_seconds`` ``max_attempts`` Fehlversuche registriert wurden."""

    def __init__(
        self,
        max_attempts: int,
        window_seconds: float,
        lockout_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.max_attempts = max_attempts
        self.window = window_seconds
        self.lockout = lockout_seconds
        self._clock = clock
        self._failures: dict[str, deque[float]] = {}
        self._locked_until: dict[str, float] = {}
        self._lock = threading.Lock()

    def retry_after(self, key: str) -> float:
        """0, wenn der Schlüssel nicht gesperrt ist, sonst verbleibende Sekunden."""
        now = self._clock()
        with self._lock:
            until = self._locked_until.get(key)
            if until is None:
                return 0.0
            if until <= now:
                del self._locked_until[key]
                return 0.0
            return until - now

    def register_failure(self, key: str) -> None:
        now = self._clock()
        with self._lock:
            attempts = self._failures.setdefault(key, deque())
            attempts.append(now)
            while attempts and attempts[0] <= now - self.window:
                attempts.popleft()
            if len(attempts) >= self.max_attempts:
                self._locked_until[key] = now + self.lockout
                attempts.clear()
            self._prune(now)

    def reset(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)
            self._locked_until.pop(key, None)

    def _prune(self, now: float) -> None:
        if len(self._failures) < 10_000:
            return
        for key in [k for k, v in self._failures.items() if not v or v[-1] <= now - self.window]:
            del self._failures[key]
        for key in [k for k, until in self._locked_until.items() if until <= now]:
            del self._locked_until[key]

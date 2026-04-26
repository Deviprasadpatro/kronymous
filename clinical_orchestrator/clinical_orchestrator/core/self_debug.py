"""Self-debug / auto-recovery primitives.

Wraps every agent call with:

* exponential-backoff retries on transient errors
* a circuit breaker that opens after repeated failures and auto-resets after
  a cool-down so a recovered agent comes back online without manual restart
* a structured failure log surfaced via the ``/health`` endpoint

The goal is to satisfy the brief's "recorrect debug automatically if anything
trouble shoots in the system" requirement without external dependencies.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, TypeVar

T = TypeVar("T")


class CircuitOpenError(RuntimeError):
    """Raised when a call is short-circuited because the breaker is open."""


@dataclass
class _BreakerState:
    failures: int = 0
    opened_at: float | None = None
    last_error: str | None = None
    successes: int = 0
    total_calls: int = 0


@dataclass
class FailureRecord:
    component: str
    error: str
    attempt: int
    timestamp: float = field(default_factory=time.time)


class SelfDebugger:
    """Per-component retry + circuit breaker."""

    def __init__(
        self,
        max_attempts: int = 3,
        base_delay: float = 0.05,
        breaker_threshold: int = 5,
        breaker_cooldown: float = 5.0,
    ) -> None:
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.breaker_threshold = breaker_threshold
        self.breaker_cooldown = breaker_cooldown
        self._states: dict[str, _BreakerState] = {}
        self._failures: list[FailureRecord] = []
        self._lock = threading.RLock()

    def _state(self, component: str) -> _BreakerState:
        with self._lock:
            return self._states.setdefault(component, _BreakerState())

    def _check_breaker(self, component: str) -> None:
        state = self._state(component)
        if state.opened_at is None:
            return
        if time.time() - state.opened_at >= self.breaker_cooldown:
            # half-open: allow a probe call
            state.opened_at = None
            state.failures = 0
            return
        raise CircuitOpenError(f"Circuit open for component '{component}': {state.last_error}")

    def call(self, component: str, fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        """Run ``fn(*args, **kwargs)`` with retries + breaker for *component*."""
        self._check_breaker(component)
        state = self._state(component)
        with self._lock:
            state.total_calls += 1

        last_err: BaseException | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                result = fn(*args, **kwargs)
                with self._lock:
                    state.successes += 1
                    state.failures = 0
                    state.last_error = None
                return result
            except CircuitOpenError:
                raise
            except Exception as exc:
                last_err = exc
                with self._lock:
                    state.failures += 1
                    state.last_error = f"{type(exc).__name__}: {exc}"
                    self._failures.append(
                        FailureRecord(component=component, error=state.last_error, attempt=attempt)
                    )
                    if state.failures >= self.breaker_threshold:
                        state.opened_at = time.time()
                if attempt < self.max_attempts:
                    time.sleep(self.base_delay * (2 ** (attempt - 1)))
                    continue
                break

        # Exhausted retries
        assert last_err is not None
        raise last_err

    # -- health introspection -------------------------------------------
    def health(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            return {
                name: {
                    "status": "open" if s.opened_at is not None else "closed",
                    "failures": s.failures,
                    "successes": s.successes,
                    "total_calls": s.total_calls,
                    "last_error": s.last_error,
                    "opened_at": s.opened_at,
                }
                for name, s in self._states.items()
            }

    def recent_failures(self, limit: int = 50) -> list[FailureRecord]:
        with self._lock:
            return list(self._failures[-limit:])

    def reset(self, component: str | None = None) -> None:
        with self._lock:
            if component is None:
                self._states.clear()
                self._failures.clear()
            else:
                self._states.pop(component, None)

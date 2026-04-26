"""Lightweight publish/subscribe event bus for cross-agent collaboration.

Every agent in the Clinical Orchestrator publishes structured ``ClinicalEvent``s
to the bus (e.g. ``diagnostic.finding``, ``vitals.deviation``,
``documentation.update``) and may subscribe to events from any other module.

The bus is intentionally in-process and dependency-free so it works in tests
and offline CI; for production it can be swapped for Redis / Kafka / NATS by
re-implementing :class:`EventBus` with the same interface.
"""

from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ClinicalEvent:
    """A single message on the cross-collaboration bus."""

    topic: str
    payload: dict[str, Any]
    source: str = "unknown"
    patient_id: str | None = None
    severity: str = "info"  # info | notice | warning | critical
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)


Handler = Callable[[ClinicalEvent], None]


class EventBus:
    """Thread-safe in-process pub/sub.

    Topic strings use dotted namespaces (``module.action``). Subscribers may
    use ``"*"`` as a wildcard segment, e.g. ``"diagnostic.*"`` matches any
    ``diagnostic.<x>`` topic.
    """

    def __init__(self) -> None:
        self._subs: dict[str, list[Handler]] = {}
        self._history: list[ClinicalEvent] = []
        self._lock = threading.RLock()

    # -- subscription ----------------------------------------------------
    def subscribe(self, pattern: str, handler: Handler) -> Callable[[], None]:
        with self._lock:
            self._subs.setdefault(pattern, []).append(handler)

        def _unsubscribe() -> None:
            with self._lock:
                if pattern in self._subs and handler in self._subs[pattern]:
                    self._subs[pattern].remove(handler)

        return _unsubscribe

    # -- publication -----------------------------------------------------
    def publish(self, event: ClinicalEvent) -> None:
        """Publish *event* to all matching subscribers.

        Subscriber exceptions are caught so a misbehaving handler cannot
        bring down the whole orchestrator — this is part of the
        "self-debug / auto-recovery" guarantee.
        """
        with self._lock:
            self._history.append(event)
            handlers = list(self._matching_handlers(event.topic))

        for handler in handlers:
            try:
                handler(event)
            except Exception as exc:  # pragma: no cover - defensive
                # Re-publish as a system error event so self-debug can react.
                if event.topic != "system.handler_error":
                    self.publish(
                        ClinicalEvent(
                            topic="system.handler_error",
                            source="event_bus",
                            payload={"original_topic": event.topic, "error": str(exc)},
                            severity="warning",
                        )
                    )

    def _matching_handlers(self, topic: str):
        parts = topic.split(".")
        for pattern, handlers in self._subs.items():
            if _match(pattern, parts):
                yield from handlers

    # -- introspection ---------------------------------------------------
    def history(self, topic_prefix: str | None = None) -> list[ClinicalEvent]:
        with self._lock:
            if topic_prefix is None:
                return list(self._history)
            return [e for e in self._history if e.topic.startswith(topic_prefix)]

    def clear(self) -> None:
        with self._lock:
            self._history.clear()


def _match(pattern: str, parts: list[str]) -> bool:
    pat_parts = pattern.split(".")
    if len(pat_parts) != len(parts):
        # allow trailing wildcard "diagnostic.*" to match deeper topics
        if pat_parts[-1] == "*" and len(pat_parts) <= len(parts):
            return all(p == "*" or p == parts[i] for i, p in enumerate(pat_parts[:-1]))
        return False
    return all(p == "*" or p == parts[i] for i, p in enumerate(pat_parts))

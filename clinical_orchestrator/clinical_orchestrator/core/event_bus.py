"""Lightweight publish/subscribe event bus for cross-agent collaboration.

Every agent in the Clinical Orchestrator publishes structured ``ClinicalEvent``s
to the bus (e.g. ``diagnostic.finding``, ``vitals.deviation``,
``documentation.update``) and may subscribe to events from any other module.

The bus delegates transport to a :class:`~.bus_backend.BusBackend`. The default
backend is in-process and dependency-free (so tests and offline CI just work);
multi-host deployments can swap in Redis Streams or Kafka via
``CLINICAL_BUS_URL`` without changing any agent code.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover
    from .bus_backend import BusBackend


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
    """Thread-safe pub/sub fronting a pluggable transport backend.

    Topic strings use dotted namespaces (``module.action``). Subscribers may
    use ``"*"`` as a wildcard segment, e.g. ``"diagnostic.*"`` matches any
    ``diagnostic.<x>`` topic.
    """

    def __init__(self, backend: BusBackend | None = None) -> None:
        if backend is None:
            from .bus_backend import make_backend
            backend = make_backend()
        self.backend = backend

    @property
    def transport(self) -> str:
        return getattr(self.backend, "name", "memory")

    # -- subscription ----------------------------------------------------
    def subscribe(self, pattern: str, handler: Handler) -> Callable[[], None]:
        return self.backend.subscribe(pattern, handler)

    # -- publication -----------------------------------------------------
    def publish(self, event: ClinicalEvent) -> None:
        """Publish *event* to all matching subscribers (local + remote)."""
        self.backend.publish(event)

    # -- introspection ---------------------------------------------------
    def history(self, topic_prefix: str | None = None) -> list[ClinicalEvent]:
        return self.backend.history(topic_prefix)

    def clear(self) -> None:
        self.backend.clear()

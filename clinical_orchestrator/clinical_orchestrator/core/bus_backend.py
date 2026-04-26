"""Pluggable transport backends for the Clinical Orchestrator EventBus.

The default :class:`EventBus` ships with an in-process backend that
preserves the original single-process behavior. For multi-host
orchestration, callers can opt into a Redis Streams or Kafka backend by
setting ``CLINICAL_BUS_URL``:

    memory://                                  # default
    redis://[user:pass@]host:6379/0?stream=clinical
    kafka://broker1:9092,broker2:9092?topic=clinical&group=orchestrator

All backends implement the same :class:`BusBackend` Protocol so the
``EventBus`` API is unchanged.

The in-process backend is mandatory; Redis / Kafka are imported lazily and
fall back to in-process if their library or broker is unreachable
(consistent with the rest of the system's "self-debug + degrade
gracefully" stance).
"""

from __future__ import annotations

import json
import os
import threading
import time
from collections.abc import Callable
from dataclasses import asdict
from typing import TYPE_CHECKING, Any, Protocol
from urllib.parse import parse_qs, urlparse

if TYPE_CHECKING:  # pragma: no cover
    from .event_bus import ClinicalEvent

Handler = Callable[["ClinicalEvent"], None]


class BusBackend(Protocol):
    """Common transport interface used by :class:`EventBus`."""

    name: str

    def publish(self, event: ClinicalEvent) -> None: ...
    def subscribe(self, pattern: str, handler: Handler) -> Callable[[], None]: ...
    def history(self, topic_prefix: str | None = None) -> list[ClinicalEvent]: ...
    def clear(self) -> None: ...
    def close(self) -> None: ...


# ---------------------------------------------------------------------------
# In-process (default) backend — encapsulates the historical EventBus logic
# ---------------------------------------------------------------------------


class InProcessBackend:
    name = "memory"

    def __init__(self) -> None:
        self._subs: dict[str, list[Handler]] = {}
        self._history: list[ClinicalEvent] = []
        self._lock = threading.RLock()

    def publish(self, event: ClinicalEvent) -> None:
        with self._lock:
            self._history.append(event)
            handlers = list(self._matching_handlers(event.topic))
        for handler in handlers:
            try:
                handler(event)
            except Exception as exc:  # pragma: no cover - defensive
                if event.topic != "system.handler_error":
                    from .event_bus import ClinicalEvent as CE
                    self.publish(
                        CE(
                            topic="system.handler_error",
                            source="event_bus",
                            payload={"original_topic": event.topic, "error": str(exc)},
                            severity="warning",
                        )
                    )

    def subscribe(self, pattern: str, handler: Handler) -> Callable[[], None]:
        with self._lock:
            self._subs.setdefault(pattern, []).append(handler)

        def _unsub() -> None:
            with self._lock:
                if pattern in self._subs and handler in self._subs[pattern]:
                    self._subs[pattern].remove(handler)

        return _unsub

    def history(self, topic_prefix: str | None = None) -> list[ClinicalEvent]:
        with self._lock:
            if topic_prefix is None:
                return list(self._history)
            return [e for e in self._history if e.topic.startswith(topic_prefix)]

    def clear(self) -> None:
        with self._lock:
            self._history.clear()

    def close(self) -> None:  # pragma: no cover
        pass

    def _matching_handlers(self, topic: str):
        parts = topic.split(".")
        for pattern, handlers in self._subs.items():
            if _match(pattern, parts):
                yield from handlers


def _match(pattern: str, parts: list[str]) -> bool:
    pat_parts = pattern.split(".")
    if len(pat_parts) != len(parts):
        if pat_parts[-1] == "*" and len(pat_parts) <= len(parts):
            return all(p == "*" or p == parts[i] for i, p in enumerate(pat_parts[:-1]))
        return False
    return all(p == "*" or p == parts[i] for i, p in enumerate(pat_parts))


# ---------------------------------------------------------------------------
# Redis Streams backend
# ---------------------------------------------------------------------------


class RedisBackend:
    """Redis Streams transport (XADD / XREAD).

    Local subscribers still receive events synchronously (so cross-collab
    handlers fire on the publisher's host), AND a background reader pulls
    remote events from Redis and dispatches them to local subscribers. This
    gives single-process tests the same semantics while transparently
    multi-hosting.
    """

    name = "redis"

    def __init__(self, url: str, stream: str = "clinical") -> None:
        self.url = url
        self.stream = stream
        self._inproc = InProcessBackend()
        self._client: Any | None = None
        self._reader_thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._self_id = f"{os.getpid()}.{int(time.time() * 1000)}"
        self._connect()

    def _connect(self) -> None:
        try:
            import redis  # type: ignore
        except Exception:
            self._client = None
            return
        try:
            self._client = redis.from_url(self.url, decode_responses=True)
            # Verify connection eagerly.
            self._client.ping()
        except Exception:
            self._client = None
            return
        # Start background consumer.
        self._reader_thread = threading.Thread(
            target=self._reader_loop, name="bus-redis-reader", daemon=True
        )
        self._reader_thread.start()

    def _reader_loop(self) -> None:  # pragma: no cover - depends on broker
        last_id = "$"
        while not self._stop.is_set():
            try:
                resp = self._client.xread({self.stream: last_id}, block=500, count=64)
            except Exception:
                time.sleep(0.5)
                continue
            if not resp:
                continue
            for _stream, entries in resp:
                for entry_id, fields in entries:
                    last_id = entry_id
                    if fields.get("origin") == self._self_id:
                        continue  # skip our own emissions
                    try:
                        event = _event_from_fields(fields)
                    except Exception:
                        continue
                    self._inproc.publish(event)

    def publish(self, event: ClinicalEvent) -> None:
        self._inproc.publish(event)
        if self._client is None:
            return
        try:
            self._client.xadd(self.stream, _event_to_fields(event, self._self_id), maxlen=10_000)
        except Exception:
            # transport failure is non-fatal; in-process delivery already happened
            pass

    def subscribe(self, pattern: str, handler: Handler) -> Callable[[], None]:
        return self._inproc.subscribe(pattern, handler)

    def history(self, topic_prefix: str | None = None) -> list[ClinicalEvent]:
        return self._inproc.history(topic_prefix)

    def clear(self) -> None:
        self._inproc.clear()

    def close(self) -> None:  # pragma: no cover
        self._stop.set()
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Kafka backend
# ---------------------------------------------------------------------------


class KafkaBackend:
    """Confluent-Kafka transport (or aiokafka if installed).

    Same semantics as the Redis backend — local synchronous fan-out plus a
    background consumer for cross-host events.
    """

    name = "kafka"

    def __init__(self, brokers: str, topic: str = "clinical", group: str = "orchestrator") -> None:
        self.brokers = brokers
        self.topic = topic
        self.group = group
        self._inproc = InProcessBackend()
        self._producer: Any | None = None
        self._consumer: Any | None = None
        self._reader_thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._self_id = f"{os.getpid()}.{int(time.time() * 1000)}"
        self._connect()

    def _connect(self) -> None:
        try:
            from confluent_kafka import Consumer, Producer  # type: ignore
        except Exception:
            self._producer = None
            self._consumer = None
            return
        try:
            self._producer = Producer({"bootstrap.servers": self.brokers})
            self._consumer = Consumer(
                {
                    "bootstrap.servers": self.brokers,
                    "group.id": self.group,
                    "auto.offset.reset": "latest",
                    "enable.auto.commit": True,
                }
            )
            self._consumer.subscribe([self.topic])
        except Exception:
            self._producer = None
            self._consumer = None
            return
        self._reader_thread = threading.Thread(
            target=self._reader_loop, name="bus-kafka-reader", daemon=True
        )
        self._reader_thread.start()

    def _reader_loop(self) -> None:  # pragma: no cover - depends on broker
        while not self._stop.is_set():
            msg = self._consumer.poll(timeout=0.5)
            if msg is None or msg.error():
                continue
            try:
                payload = json.loads(msg.value())
            except Exception:
                continue
            if payload.get("origin") == self._self_id:
                continue
            try:
                event = _event_from_dict(payload)
            except Exception:
                continue
            self._inproc.publish(event)

    def publish(self, event: ClinicalEvent) -> None:
        self._inproc.publish(event)
        if self._producer is None:
            return
        try:
            payload = _event_to_dict(event, self._self_id)
            self._producer.produce(self.topic, json.dumps(payload).encode("utf-8"))
            self._producer.poll(0)
        except Exception:
            pass

    def subscribe(self, pattern: str, handler: Handler) -> Callable[[], None]:
        return self._inproc.subscribe(pattern, handler)

    def history(self, topic_prefix: str | None = None) -> list[ClinicalEvent]:
        return self._inproc.history(topic_prefix)

    def clear(self) -> None:
        self._inproc.clear()

    def close(self) -> None:  # pragma: no cover
        self._stop.set()
        if self._consumer is not None:
            try:
                self._consumer.close()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Serialization helpers (Redis hash fields & Kafka JSON payloads)
# ---------------------------------------------------------------------------


def _event_to_fields(event: ClinicalEvent, origin: str) -> dict[str, str]:
    return {
        "event_id": event.event_id,
        "topic": event.topic,
        "source": event.source,
        "patient_id": event.patient_id or "",
        "severity": event.severity,
        "timestamp": str(event.timestamp),
        "payload": json.dumps(event.payload),
        "origin": origin,
    }


def _event_from_fields(fields: dict[str, str]) -> ClinicalEvent:
    from .event_bus import ClinicalEvent as CE
    return CE(
        topic=fields["topic"],
        payload=json.loads(fields.get("payload", "{}")),
        source=fields.get("source", "unknown"),
        patient_id=fields.get("patient_id") or None,
        severity=fields.get("severity", "info"),
        event_id=fields.get("event_id", ""),
        timestamp=float(fields.get("timestamp", "0") or 0.0),
    )


def _event_to_dict(event: ClinicalEvent, origin: str) -> dict[str, Any]:
    d = asdict(event)
    d["origin"] = origin
    return d


def _event_from_dict(d: dict[str, Any]) -> ClinicalEvent:
    from .event_bus import ClinicalEvent as CE
    return CE(
        topic=d["topic"],
        payload=d.get("payload", {}),
        source=d.get("source", "unknown"),
        patient_id=d.get("patient_id"),
        severity=d.get("severity", "info"),
        event_id=d.get("event_id", ""),
        timestamp=d.get("timestamp", 0.0),
    )


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def make_backend(url: str | None = None) -> BusBackend:
    """Construct a bus backend from a URL or env (``CLINICAL_BUS_URL``)."""
    url = url or os.environ.get("CLINICAL_BUS_URL") or "memory://"
    if url.startswith("memory://"):
        return InProcessBackend()
    if url.startswith("redis://") or url.startswith("rediss://"):
        parsed = urlparse(url)
        qs = parse_qs(parsed.query or "")
        stream = (qs.get("stream") or ["clinical"])[0]
        # Strip query string from the URL passed to redis-py.
        sanitized = url.split("?", 1)[0]
        be = RedisBackend(sanitized, stream=stream)
        # If client failed to connect, degrade gracefully to in-process.
        if be._client is None:
            return InProcessBackend()
        return be
    if url.startswith("kafka://"):
        # kafka://broker1:9092,broker2:9092?topic=foo&group=bar
        parsed = urlparse(url)
        brokers = parsed.netloc or parsed.path.lstrip("/")
        qs = parse_qs(parsed.query or "")
        topic = (qs.get("topic") or ["clinical"])[0]
        group = (qs.get("group") or ["orchestrator"])[0]
        be = KafkaBackend(brokers=brokers, topic=topic, group=group)
        if be._producer is None:
            return InProcessBackend()
        return be
    raise ValueError(f"Unsupported bus URL: {url!r}")

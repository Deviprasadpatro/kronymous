"""Tests for the pluggable EventBus backends."""

from __future__ import annotations

import pytest

from clinical_orchestrator.core.bus_backend import (
    InProcessBackend,
    KafkaBackend,
    RedisBackend,
    make_backend,
)
from clinical_orchestrator.core.event_bus import ClinicalEvent, EventBus


def test_make_backend_default_memory(monkeypatch):
    monkeypatch.delenv("CLINICAL_BUS_URL", raising=False)
    be = make_backend()
    assert isinstance(be, InProcessBackend)
    assert be.name == "memory"


def test_make_backend_unknown_url_raises():
    with pytest.raises(ValueError):
        make_backend("ftp://nowhere")


def test_eventbus_in_process_publish_subscribe():
    bus = EventBus()
    received: list[ClinicalEvent] = []
    bus.subscribe("test.*", received.append)
    e = ClinicalEvent(topic="test.fired", payload={"k": "v"}, source="t", patient_id="P")
    bus.publish(e)
    assert len(received) == 1
    assert received[0].payload == {"k": "v"}
    assert bus.transport == "memory"


def test_redis_backend_degrades_to_in_process(monkeypatch):
    """make_backend must degrade gracefully when redis is unreachable.

    No redis broker is available in CI; the factory should hand back an
    InProcessBackend rather than a half-initialized RedisBackend.
    """
    be = make_backend("redis://127.0.0.1:1/0")
    # Either redis-py is missing OR ping fails — both are degraded paths.
    assert isinstance(be, InProcessBackend)


def test_kafka_backend_degrades_to_in_process():
    """Same graceful-degrade contract as Redis."""
    be = make_backend("kafka://127.0.0.1:1?topic=x&group=y")
    assert isinstance(be, InProcessBackend)


def test_redis_backend_no_lib_does_not_crash(monkeypatch):
    """Constructing RedisBackend directly without the lib must not raise.

    The instance simply has ``_client is None`` and falls through to
    in-process delivery. This is what guarantees we can import bus_backend
    in any environment.
    """
    be = RedisBackend("redis://127.0.0.1:65535/0")
    received: list[ClinicalEvent] = []
    be.subscribe("test.*", received.append)
    be.publish(ClinicalEvent(topic="test.fired", payload={}, source="t"))
    assert len(received) == 1


def test_kafka_backend_no_lib_does_not_crash():
    """Same contract as RedisBackend."""
    be = KafkaBackend(brokers="127.0.0.1:65535", topic="x")
    received: list[ClinicalEvent] = []
    be.subscribe("test.*", received.append)
    be.publish(ClinicalEvent(topic="test.fired", payload={}, source="t"))
    assert len(received) == 1

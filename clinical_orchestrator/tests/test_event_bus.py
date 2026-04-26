from clinical_orchestrator.core.event_bus import ClinicalEvent, EventBus


def test_topic_match_exact():
    bus = EventBus()
    seen = []
    bus.subscribe("a.b", lambda e: seen.append(e.topic))
    bus.publish(ClinicalEvent(topic="a.b", payload={}))
    bus.publish(ClinicalEvent(topic="a.c", payload={}))
    assert seen == ["a.b"]


def test_topic_match_wildcard_segment():
    bus = EventBus()
    seen = []
    bus.subscribe("a.*", lambda e: seen.append(e.topic))
    bus.publish(ClinicalEvent(topic="a.b", payload={}))
    bus.publish(ClinicalEvent(topic="a.c", payload={}))
    bus.publish(ClinicalEvent(topic="x.b", payload={}))
    assert sorted(seen) == ["a.b", "a.c"]


def test_handler_exception_does_not_crash_bus():
    bus = EventBus()
    good = []

    def bad_handler(_e):
        raise RuntimeError("boom")

    def good_handler(e):
        good.append(e.topic)

    bus.subscribe("x.y", bad_handler)
    bus.subscribe("x.y", good_handler)
    bus.publish(ClinicalEvent(topic="x.y", payload={}))
    assert good == ["x.y"]
    # And a system.handler_error event should now be on the bus.
    assert any(e.topic == "system.handler_error" for e in bus.history())


def test_unsubscribe():
    bus = EventBus()
    seen = []
    off = bus.subscribe("z", lambda e: seen.append(1))
    bus.publish(ClinicalEvent(topic="z", payload={}))
    off()
    bus.publish(ClinicalEvent(topic="z", payload={}))
    assert seen == [1]

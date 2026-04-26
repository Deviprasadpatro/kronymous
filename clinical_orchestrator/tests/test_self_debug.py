import pytest

from clinical_orchestrator.core.self_debug import CircuitOpenError, SelfDebugger


def test_retries_then_succeeds():
    dbg = SelfDebugger(max_attempts=3, base_delay=0.0)
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("transient")
        return "ok"

    assert dbg.call("c", flaky) == "ok"
    assert dbg.health()["c"]["successes"] == 1


def test_exhausted_retries_raises_last_error():
    dbg = SelfDebugger(max_attempts=2, base_delay=0.0)

    def always_fail():
        raise ValueError("nope")

    with pytest.raises(ValueError):
        dbg.call("c", always_fail)
    assert dbg.health()["c"]["failures"] == 2


def test_circuit_breaker_opens_then_recovers():
    dbg = SelfDebugger(max_attempts=1, base_delay=0.0, breaker_threshold=2, breaker_cooldown=0.05)

    def boom():
        raise RuntimeError("x")

    with pytest.raises(RuntimeError):
        dbg.call("c", boom)
    with pytest.raises(RuntimeError):
        dbg.call("c", boom)
    # Now circuit is open; further call short-circuits.
    with pytest.raises(CircuitOpenError):
        dbg.call("c", boom)
    # After cooldown, next call passes through (half-open) and either succeeds or fails normally.
    import time
    time.sleep(0.1)

    def ok():
        return 42

    assert dbg.call("c", ok) == 42
    assert dbg.health()["c"]["status"] == "closed"

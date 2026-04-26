import pytest

from clinical_orchestrator.core.safety import SafetyGate


def test_propose_then_confirm():
    gate = SafetyGate()
    a = gate.propose("doc", "x", "rationale", ["evidence"], {"k": 1}, severity="notice")
    assert a.status == "pending"
    out = gate.confirm(a.action_id, reviewer="rn1")
    assert out.status == "confirmed"
    assert out.final_action == {"k": 1}
    assert out.reviewer == "rn1"


def test_modify_overrides_payload():
    gate = SafetyGate()
    a = gate.propose("doc", "x", "r", [], {"k": 1})
    out = gate.modify(a.action_id, "rn1", {"k": 2})
    assert out.status == "modified"
    assert out.final_action == {"k": 2}


def test_reject():
    gate = SafetyGate()
    a = gate.propose("doc", "x", "r", [], {"k": 1})
    out = gate.reject(a.action_id, "rn1")
    assert out.status == "rejected"
    assert out.final_action is None


def test_double_review_raises():
    gate = SafetyGate()
    a = gate.propose("doc", "x", "r", [], {"k": 1})
    gate.confirm(a.action_id, "rn1")
    with pytest.raises(ValueError):
        gate.confirm(a.action_id, "rn2")


def test_pending_filters_by_patient():
    gate = SafetyGate()
    a = gate.propose("doc", "x", "r", [], {}, patient_id="P1")
    gate.propose("doc", "x", "r", [], {}, patient_id="P2")
    out = gate.pending(patient_id="P1")
    assert len(out) == 1
    assert out[0].action_id == a.action_id

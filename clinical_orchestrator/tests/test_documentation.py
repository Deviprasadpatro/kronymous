from clinical_orchestrator.agents.documentation import DocumentationAgent
from clinical_orchestrator.core.audit import AuditLog
from clinical_orchestrator.core.context import PatientContext
from clinical_orchestrator.core.event_bus import EventBus
from clinical_orchestrator.core.safety import SafetyGate


def _agent():
    bus = EventBus()
    return DocumentationAgent(bus, SafetyGate(), AuditLog()), bus


def test_explicit_soap_markers_parsed():
    agent, _ = _agent()
    p = PatientContext(patient_id="P1", conditions=["hypertension"])
    transcript = (
        "S: Headache 3 days.\n"
        "O: BP 150/95, HR 80.\n"
        "A: Likely uncontrolled hypertension.\n"
        "P: Increase lisinopril; follow-up in 2 weeks."
    )
    out = agent.run(transcript, p)
    draft = out["draft"]
    assert "Headache" in draft["soap"]["subjective"]
    assert "BP 150/95" in draft["soap"]["objective"]
    assert "hypertension" in draft["soap"]["assessment"].lower()
    assert "lisinopril" in draft["soap"]["plan"].lower()
    # ICD-10: hypertension keyword triggers I10.
    assert any(c["code"] == "I10" for c in draft["icd10"])


def test_heuristic_split_when_no_markers():
    agent, _ = _agent()
    p = PatientContext(patient_id="P1")
    transcript = (
        "Patient reports chest pain. BP 150/95, HR 100. Likely hypertension. "
        "Plan to start lisinopril."
    )
    out = agent.run(transcript, p)
    soap = out["draft"]["soap"]
    assert soap["objective"]
    assert soap["assessment"]
    assert soap["plan"]


def test_apply_finding_appends_to_assessment():
    agent, _ = _agent()
    p = PatientContext(patient_id="P1")
    p.soap_note["assessment"] = "Initial assessment."
    agent.apply_finding(p, "New imaging finding: cardiomegaly")
    assert "cardiomegaly" in p.soap_note["assessment"]
    assert "Initial assessment" in p.soap_note["assessment"]


def test_health_check():
    agent, _ = _agent()
    assert agent.health_check() is True

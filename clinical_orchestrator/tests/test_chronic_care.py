from clinical_orchestrator.agents.chronic_care import ChronicCareAgent
from clinical_orchestrator.core.audit import AuditLog
from clinical_orchestrator.core.context import LabResult, PatientContext, VitalReading
from clinical_orchestrator.core.event_bus import EventBus
from clinical_orchestrator.core.safety import SafetyGate


def _agent():
    return ChronicCareAgent(EventBus(), SafetyGate(), AuditLog())


def test_no_deviation_when_in_range():
    agent = _agent()
    p = PatientContext(patient_id="P1", conditions=["hypertension"])
    p.add_vital(VitalReading(name="systolic_bp", value=120, unit="mmHg"))
    p.add_vital(VitalReading(name="spo2", value=98, unit="%"))
    out = agent.run(p)
    assert out["suggestion"]["deviations"] == []
    assert out["severity"] == "notice"


def test_critical_spo2_drives_critical_severity():
    agent = _agent()
    p = PatientContext(patient_id="P1")
    p.add_vital(VitalReading(name="spo2", value=88, unit="%"))
    out = agent.run(p)
    assert out["severity"] == "critical"
    assert any(d["metric"] == "spo2" for d in out["suggestion"]["deviations"])
    assert any("Escalate" in r for r in out["suggestion"]["recommendations"])


def test_recommendations_match_conditions():
    agent = _agent()
    p = PatientContext(patient_id="P1", conditions=["type 2 diabetes"], allergies=["penicillin"])
    p.add_lab(LabResult(name="hba1c", value=8.2, unit="%"))
    out = agent.run(p)
    recs = out["suggestion"]["recommendations"]
    # Diabetes recs present.
    assert any("A1c" in r or "GLP-1" in r or "carb" in r.lower() for r in recs)
    # Allergy guardrail present.
    assert any("penicillin" in r for r in recs)


def test_kpi_deltas_for_heart_failure_patient():
    """Canonical 'heart failure' (with space) — the form used in cli/demo and orchestrator tests."""
    agent = _agent()
    p = PatientContext(patient_id="P1", conditions=["heart failure"])
    p.add_vital(VitalReading(name="systolic_bp", value=180, unit="mmHg"))
    p.add_lab(LabResult(name="bnp", value=900, unit="pg/mL"))
    out = agent.run(p)
    deltas = out["suggestion"]["kpi_deltas"]
    assert "alos_days" in deltas
    assert "readmission_30d_pct" in deltas


def test_kpi_deltas_for_heart_failure_alternate_spellings():
    """Underscore + CHF abbreviation should also trigger the readmission KPI."""
    agent = _agent()
    for spelling in ("heart_failure", "CHF", "Decompensated CHF exacerbation"):
        p = PatientContext(patient_id="P1", conditions=[spelling])
        p.add_vital(VitalReading(name="systolic_bp", value=180, unit="mmHg"))
        out = agent.run(p)
        assert "readmission_30d_pct" in out["suggestion"]["kpi_deltas"], (
            f"readmission KPI missing for condition spelling={spelling!r}"
        )

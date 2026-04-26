from clinical_orchestrator.agents.diagnostic import DiagnosticAgent
from clinical_orchestrator.core.audit import AuditLog
from clinical_orchestrator.core.context import PatientContext
from clinical_orchestrator.core.event_bus import EventBus
from clinical_orchestrator.core.safety import SafetyGate


def _agent():
    return DiagnosticAgent(EventBus(), SafetyGate(), AuditLog())


def test_imaging_finding_includes_spatial_ref():
    agent = _agent()
    p = PatientContext(patient_id="P1")
    out = agent.run(
        p,
        imaging_studies=[{
            "modality": "Chest X-ray",
            "image_id": "CXR-1",
            "features": ["consolidation"],
        }],
    )
    findings = out["suggestion"]["findings"]
    assert any(f["spatial_ref"] and f["spatial_ref"].get("bbox") for f in findings)
    assert "Community-acquired pneumonia" in out["suggestion"]["differential"]
    assert any("antibiotics" in s.lower() for s in out["suggestion"]["next_steps"])


def test_pathology_carcinoma_is_critical():
    agent = _agent()
    p = PatientContext(patient_id="P1")
    out = agent.run(
        p,
        pathology_reports=[{"report_id": "PATH-1", "text": "Invasive ductal carcinoma identified."}],
    )
    assert out["severity"] == "critical"
    assert "Malignancy — staging required" in out["suggestion"]["differential"]


def test_severity_is_max_not_last():
    """A later warning-level finding must not downgrade an earlier critical."""
    agent = _agent()
    # Patient with TB on the problem list -> history sub-agent emits a critical-keyword
    # finding first; then an imaging study with 'consolidation' (warning) follows.
    # Final severity must remain 'critical', not be overwritten to 'warning'.
    p = PatientContext(patient_id="P1", conditions=["tuberculosis"])
    out = agent.run(
        p,
        imaging_studies=[{
            "modality": "Chest X-ray",
            "image_id": "CXR-2",
            "features": ["consolidation"],
        }],
    )
    assert out["severity"] == "critical", (
        f"severity downgraded by later finding (got {out['severity']!r})"
    )


def test_history_subagent_emits_problem_list():
    agent = _agent()
    p = PatientContext(
        patient_id="P1",
        conditions=["hypertension"],
        medications=["lisinopril"],
        allergies=["penicillin"],
    )
    out = agent.run(p)
    descs = [f["description"] for f in out["suggestion"]["findings"]]
    assert any("Active problem list" in d for d in descs)
    assert any("Documented allergies" in d for d in descs)
    assert any("Current medications" in d for d in descs)

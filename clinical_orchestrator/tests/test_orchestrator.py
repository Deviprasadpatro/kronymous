from clinical_orchestrator import ClinicalOrchestrator


def test_end_to_end_demo_path():
    orch = ClinicalOrchestrator()
    pid = "P-T1"
    orch.upsert_patient(
        pid,
        conditions=["hypertension", "heart failure"],
        allergies=["penicillin"],
        medications=["lisinopril"],
    )

    doc_out = orch.ingest_transcript(
        pid,
        "S: Worsening dyspnea.\nO: BP 180/100, SpO2 90%.\nA: HF exacerbation.\nP: Start IV furosemide.",
    )
    assert "action_id" in doc_out

    vit_out = orch.ingest_vitals(pid, [
        {"name": "systolic_bp", "value": 180, "unit": "mmHg"},
        {"name": "spo2", "value": 90, "unit": "%"},
    ])
    assert vit_out["severity"] == "critical"

    dx_out = orch.diagnose(pid, imaging_studies=[{
        "modality": "Chest X-ray",
        "image_id": "CXR-T1",
        "features": ["cardiomegaly", "pleural effusion"],
    }])
    assert dx_out["suggestion"]["findings"]

    pending = orch.pending_reviews(patient_id=pid)
    # Doc + chronic-care (potentially re-run via cross-collab) + diagnostic
    assert len(pending) >= 3
    for p in pending:
        orch.confirm(p.action_id, reviewer="dr.test")

    patient = orch.registry.get(pid)
    assert patient is not None
    assert patient.soap_note  # documentation committed
    assert patient.codes      # ICD-10 / CPT committed
    assert patient.care_plan  # chronic-care + diagnostic recommendations
    health = orch.health()
    assert health["ok"]


def test_modify_with_empty_dict_does_not_silently_recommit_suggestion():
    """Reviewer modifying an action to `{}` must NOT re-commit the original suggestion."""
    orch = ClinicalOrchestrator()
    pid = "P-MOD"
    orch.upsert_patient(pid)
    orch.ingest_transcript(
        pid,
        "S: cough\nO: BP 130/80\nA: Hypertension under control\nP: Continue meds",
    )
    pending = orch.pending_reviews(patient_id=pid)
    assert pending, "expected at least one pending action from documentation"

    doc_action = next(a for a in pending if a.actor == "documentation")
    # Modify with empty dict -> payload should be {}, so nothing committed.
    orch.modify(doc_action.action_id, reviewer="dr.test", final_action={})

    patient = orch.registry.get(pid)
    assert patient is not None
    assert patient.codes == [], (
        f"empty-dict modify silently re-committed original suggestion; got codes={patient.codes!r}"
    )
    assert patient.soap_note == {}, (
        f"empty-dict modify silently re-committed original SOAP; got {patient.soap_note!r}"
    )


def test_cross_collab_diagnostic_finding_updates_soap():
    orch = ClinicalOrchestrator()
    pid = "P-X1"
    orch.upsert_patient(pid)
    # Seed an empty SOAP note.
    patient = orch.registry.get(pid)
    assert patient is not None
    patient.soap_note["assessment"] = "Initial."

    orch.diagnose(pid, imaging_studies=[{
        "modality": "Chest X-ray",
        "image_id": "CXR-X1",
        "features": ["consolidation"],
    }])
    assert "consolidation" in patient.soap_note["assessment"].lower() or \
           "pneumonia" in patient.soap_note["assessment"].lower()

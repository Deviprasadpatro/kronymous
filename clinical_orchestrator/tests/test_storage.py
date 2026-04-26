"""Tests for pluggable Storage (memory + sqlite)."""

from __future__ import annotations

import os

import pytest

from clinical_orchestrator.core.audit import AuditLog
from clinical_orchestrator.core.context import (
    Finding,
    LabResult,
    PatientContext,
    PatientRegistry,
    VitalReading,
)
from clinical_orchestrator.core.orchestrator import ClinicalOrchestrator
from clinical_orchestrator.core.safety import SafetyGate
from clinical_orchestrator.core.storage import (
    MemoryStorage,
    SqliteStorage,
    make_storage,
)


def _populated_patient(pid: str = "P-1") -> PatientContext:
    p = PatientContext(
        patient_id=pid,
        name="Jane Doe",
        allergies=["penicillin"],
        conditions=["heart failure"],
    )
    p.add_vital(VitalReading(name="systolic_bp", value=160, unit="mmHg"))
    p.add_lab(LabResult(name="bnp", value=820, unit="pg/mL"))
    p.add_finding(
        Finding(source="imaging.cxr", description="Cardiomegaly", confidence=0.8,
                spatial_ref={"image_id": "CXR-1", "bbox": [0, 0, 10, 10]})
    )
    return p


def test_make_storage_default_memory(monkeypatch):
    monkeypatch.delenv("CLINICAL_STORAGE_URL", raising=False)
    s = make_storage()
    assert isinstance(s, MemoryStorage)


def test_make_storage_sqlite(tmp_path):
    db = tmp_path / "co.sqlite"
    s = make_storage(f"sqlite:///{db}")
    assert isinstance(s, SqliteStorage)
    assert os.path.exists(db)
    s.close()


def test_make_storage_unknown_url_raises():
    with pytest.raises(ValueError):
        make_storage("bogus://nowhere")


def test_sqlite_round_trip_patient(tmp_path):
    db = tmp_path / "co.sqlite"
    s1 = SqliteStorage(str(db))
    p = _populated_patient()
    s1.save_patient(p)
    s1.close()

    s2 = SqliteStorage(str(db))
    loaded = s2.load_patient("P-1")
    assert loaded is not None
    assert loaded.name == "Jane Doe"
    assert "heart failure" in loaded.conditions
    assert any(v.name == "systolic_bp" and v.value == 160 for v in loaded.vitals)
    assert any(lab.name == "bnp" and lab.value == 820 for lab in loaded.labs)
    assert any(f.description == "Cardiomegaly" for f in loaded.findings)
    s2.close()


def test_registry_persists_via_sqlite(tmp_path):
    """PatientRegistry mirrors writes; restart sees the patient."""
    db = tmp_path / "co.sqlite"
    s1 = SqliteStorage(str(db))
    reg1 = PatientRegistry(storage=s1)
    p = reg1.get_or_create("P-2", name="Mark")
    p.conditions.append("diabetes")
    reg1.save(p)
    s1.close()

    s2 = SqliteStorage(str(db))
    reg2 = PatientRegistry(storage=s2)
    loaded = reg2.get("P-2")
    assert loaded is not None
    assert loaded.name == "Mark"
    assert "diabetes" in loaded.conditions
    s2.close()


def test_safety_gate_persists_pending_actions(tmp_path):
    """SafetyGate replays pending actions from sqlite on restart."""
    db = tmp_path / "co.sqlite"
    s1 = SqliteStorage(str(db))
    gate1 = SafetyGate(storage=s1)
    a = gate1.propose(
        actor="documentation",
        description="Test SOAP",
        rationale="Test",
        evidence=["evidence"],
        suggested_action={"soap": {"subjective": "S"}},
        patient_id="P-3",
    )
    s1.close()

    s2 = SqliteStorage(str(db))
    gate2 = SafetyGate(storage=s2)
    pending = gate2.pending()
    assert any(p.action_id == a.action_id for p in pending)
    s2.close()


def test_audit_log_persists(tmp_path):
    """AuditLog persists entries to sqlite and replays them on restart."""
    db = tmp_path / "co.sqlite"
    s1 = SqliteStorage(str(db))
    log1 = AuditLog(storage=s1)
    log1.record(actor="documentation", action="propose_soap", patient_id="P-4")
    s1.close()

    s2 = SqliteStorage(str(db))
    log2 = AuditLog(storage=s2)
    entries = log2.entries()
    assert any(
        e.actor == "documentation" and e.action == "propose_soap" and e.patient_id == "P-4"
        for e in entries
    )
    s2.close()


def test_orchestrator_with_sqlite_round_trip(tmp_path):
    """End-to-end: run a documentation flow on sqlite, restart, see committed state."""
    db = tmp_path / "co.sqlite"
    s1 = SqliteStorage(str(db))
    orch1 = ClinicalOrchestrator(storage=s1)
    orch1.upsert_patient("P-E2E", conditions=["hypertension"])
    out = orch1.ingest_transcript(
        "P-E2E",
        "S: chest pain\nO: BP 150/95\nA: hypertension\nP: increase lisinopril",
    )
    action_id = out["action_id"]
    orch1.confirm(action_id, reviewer="dr.test")
    s1.close()

    # Restart against the same db file.
    s2 = SqliteStorage(str(db))
    orch2 = ClinicalOrchestrator(storage=s2)
    p = orch2.registry.get("P-E2E")
    assert p is not None, "patient must survive process restart"
    assert p.codes, "ICD-10 codes must be persisted across restart"
    assert p.soap_note, "SOAP note must be persisted across restart"
    # The pending review queue must also be empty (we already confirmed).
    assert all(a.status != "pending" for a in orch2.safety.all() if a.action_id == action_id)
    s2.close()

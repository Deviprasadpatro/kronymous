"""Command-line entry point.

Usage:
    python -m clinical_orchestrator.cli demo
    python -m clinical_orchestrator.cli health
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from .core.orchestrator import ClinicalOrchestrator


def _demo() -> dict[str, Any]:
    orch = ClinicalOrchestrator()
    pid = "P-1001"
    orch.upsert_patient(
        pid,
        name="Jane Roe",
        dob="1962-04-12",
        sex="F",
        mrn="MRN-998877",
        allergies=["penicillin"],
        conditions=["hypertension", "type 2 diabetes", "heart failure"],
        medications=["lisinopril 20 mg", "metformin 1000 mg", "carvedilol 12.5 mg"],
    )

    transcript = (
        "S: Patient reports increased shortness of breath over the last 3 days, mild chest pain.\n"
        "O: BP 168/102, HR 102, SpO2 91%. Bibasilar rales on auscultation. ECG shows sinus tachycardia.\n"
        "A: Likely heart failure exacerbation with hypertension and uncontrolled diabetes.\n"
        "P: Increase carvedilol, start IV furosemide, schedule echocardiogram, follow up in 1 week."
    )
    doc = orch.ingest_transcript(pid, transcript)

    vitals = orch.ingest_vitals(pid, [
        {"name": "systolic_bp", "value": 168, "unit": "mmHg"},
        {"name": "diastolic_bp", "value": 102, "unit": "mmHg"},
        {"name": "heart_rate", "value": 102, "unit": "bpm"},
        {"name": "spo2", "value": 91, "unit": "%"},
    ])
    labs = orch.ingest_labs(pid, [
        {"name": "glucose", "value": 240, "unit": "mg/dL"},
        {"name": "potassium", "value": 5.9, "unit": "mEq/L"},
        {"name": "bnp", "value": 850, "unit": "pg/mL"},
    ])

    dx = orch.diagnose(
        pid,
        imaging_studies=[{
            "modality": "Chest X-ray",
            "image_id": "CXR-2024-0001",
            "features": ["cardiomegaly", "pleural effusion"],
        }],
        pathology_reports=[{
            "report_id": "PATH-1",
            "text": "No malignancy. Gram-positive cocci on culture.",
        }],
    )

    # Auto-approve all pending reviews as the demo "clinician".
    confirmations = []
    for pending in orch.pending_reviews(patient_id=pid):
        confirmations.append({
            "action_id": pending.action_id,
            "actor": pending.actor,
            "severity": pending.severity,
        })
        orch.confirm(pending.action_id, reviewer="dr.demo@hospital.org")

    patient = orch.registry.get(pid)
    assert patient is not None
    return {
        "documentation": doc,
        "vitals": vitals,
        "labs": labs,
        "diagnosis": dx,
        "confirmed": confirmations,
        "final_record": {
            "soap_note": patient.soap_note,
            "codes": patient.codes,
            "care_plan": patient.care_plan,
            "kpis": patient.kpis,
            "findings": [f.description for f in patient.findings],
        },
        "health": orch.health(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="clinical-orchestrator")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("demo", help="Run an end-to-end demo scenario")
    sub.add_parser("health", help="Print the orchestrator health snapshot")
    args = parser.parse_args(argv)

    if args.cmd == "demo":
        result = _demo()
    elif args.cmd == "health":
        result = ClinicalOrchestrator().health()
    else:  # pragma: no cover - argparse handles this
        parser.error(f"unknown command: {args.cmd}")
        return 2

    json.dump(result, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

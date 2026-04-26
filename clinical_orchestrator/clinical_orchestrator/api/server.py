"""FastAPI server exposing the Clinical Orchestrator."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import FastAPI, HTTPException

from ..core.orchestrator import ClinicalOrchestrator
from .schemas import (
    DiagnoseIn,
    LabsIn,
    PatientUpsert,
    ReviewIn,
    TranscriptIn,
    VitalsIn,
)


def create_app(orchestrator: ClinicalOrchestrator | None = None) -> FastAPI:
    app = FastAPI(
        title="Clinical Orchestrator",
        description="Agentic AI system for clinical documentation, chronic care, and diagnostics.",
        version="0.1.0",
    )
    orch = orchestrator or ClinicalOrchestrator()
    app.state.orchestrator = orch

    @app.get("/health")
    def health() -> dict[str, Any]:
        return orch.health()

    @app.post("/patients")
    def upsert_patient(body: PatientUpsert) -> dict[str, Any]:
        patient = orch.upsert_patient(**body.model_dump(exclude_none=True))
        return {
            "patient_id": patient.patient_id,
            "conditions": patient.conditions,
            "allergies": patient.allergies,
        }

    @app.post("/documentation")
    def documentation(body: TranscriptIn) -> dict[str, Any]:
        return orch.ingest_transcript(body.patient_id, body.transcript)

    @app.post("/vitals")
    def vitals(body: VitalsIn) -> dict[str, Any]:
        return orch.ingest_vitals(body.patient_id, [v.model_dump() for v in body.vitals])

    @app.post("/labs")
    def labs(body: LabsIn) -> dict[str, Any]:
        return orch.ingest_labs(body.patient_id, [lab.model_dump() for lab in body.labs])

    @app.post("/diagnose")
    def diagnose(body: DiagnoseIn) -> dict[str, Any]:
        return orch.diagnose(
            body.patient_id,
            imaging_studies=body.imaging_studies,
            pathology_reports=body.pathology_reports,
        )

    @app.get("/reviews")
    def reviews(patient_id: str | None = None) -> list[dict[str, Any]]:
        return [asdict(p) for p in orch.pending_reviews(patient_id=patient_id)]

    @app.post("/reviews/{action_id}/confirm")
    def confirm(action_id: str, body: ReviewIn) -> dict[str, Any]:
        try:
            return asdict(orch.confirm(action_id, body.reviewer))
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/reviews/{action_id}/modify")
    def modify(action_id: str, body: ReviewIn) -> dict[str, Any]:
        if body.final_action is None:
            raise HTTPException(status_code=400, detail="final_action required for modify")
        try:
            return asdict(orch.modify(action_id, body.reviewer, body.final_action))
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/reviews/{action_id}/reject")
    def reject(action_id: str, body: ReviewIn) -> dict[str, Any]:
        try:
            return asdict(orch.reject(action_id, body.reviewer))
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/patients/{patient_id}")
    def get_patient(patient_id: str) -> dict[str, Any]:
        patient = orch.registry.get(patient_id)
        if not patient:
            raise HTTPException(status_code=404, detail="patient not found")
        return {
            "patient_id": patient.patient_id,
            "conditions": patient.conditions,
            "allergies": patient.allergies,
            "medications": patient.medications,
            "soap_note": patient.soap_note,
            "codes": patient.codes,
            "care_plan": patient.care_plan,
            "kpis": patient.kpis,
            "vital_count": len(patient.vitals),
            "lab_count": len(patient.labs),
            "finding_count": len(patient.findings),
        }

    return app


app = create_app()

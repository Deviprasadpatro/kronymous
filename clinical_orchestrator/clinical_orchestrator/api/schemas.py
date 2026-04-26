"""Pydantic models exposed by the FastAPI server."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class PatientUpsert(BaseModel):
    patient_id: str
    name: str | None = None
    dob: str | None = None
    sex: str | None = None
    mrn: str | None = None
    allergies: list[str] | None = None
    conditions: list[str] | None = None
    medications: list[str] | None = None


class TranscriptIn(BaseModel):
    patient_id: str
    transcript: str = Field(..., min_length=1)


class VitalIn(BaseModel):
    name: str
    value: float
    unit: str = ""


class VitalsIn(BaseModel):
    patient_id: str
    vitals: list[VitalIn]


class LabIn(BaseModel):
    name: str
    value: float
    unit: str = ""
    reference_low: float | None = None
    reference_high: float | None = None


class LabsIn(BaseModel):
    patient_id: str
    labs: list[LabIn]


class DiagnoseIn(BaseModel):
    patient_id: str
    imaging_studies: list[dict[str, Any]] | None = None
    pathology_reports: list[dict[str, Any]] | None = None


class ReviewIn(BaseModel):
    reviewer: str
    final_action: dict[str, Any] | None = None

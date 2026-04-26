"""Shared, longitudinal patient context.

Every agent reads / writes the same :class:`PatientContext` to satisfy the
"contextual awareness" directive: allergies, conditions, medications,
recent vitals, and findings are all visible across modules.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover
    from .storage import Storage


@dataclass
class VitalReading:
    name: str
    value: float
    unit: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class LabResult:
    name: str
    value: float
    unit: str
    reference_low: float | None = None
    reference_high: float | None = None
    timestamp: float = field(default_factory=time.time)


@dataclass
class Finding:
    source: str  # which agent / sub-agent
    description: str
    confidence: float = 0.0
    spatial_ref: dict[str, Any] | None = None  # e.g. {"image_id": "...", "bbox": [...]}
    citations: list[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)


@dataclass
class PatientContext:
    """Longitudinal record passed by reference across agents."""

    patient_id: str
    name: str = ""
    dob: str = ""
    sex: str = ""
    mrn: str = ""
    allergies: list[str] = field(default_factory=list)
    conditions: list[str] = field(default_factory=list)
    medications: list[str] = field(default_factory=list)
    vitals: list[VitalReading] = field(default_factory=list)
    labs: list[LabResult] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    soap_note: dict[str, str] = field(default_factory=dict)  # S/O/A/P sections
    codes: list[dict[str, str]] = field(default_factory=list)  # [{system, code, description}]
    care_plan: list[str] = field(default_factory=list)
    kpis: dict[str, float] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False, compare=False)

    # ---- thread-safe mutators ------------------------------------------
    def add_vital(self, v: VitalReading) -> None:
        with self._lock:
            self.vitals.append(v)

    def add_lab(self, lab: LabResult) -> None:
        with self._lock:
            self.labs.append(lab)

    def add_finding(self, f: Finding) -> None:
        with self._lock:
            self.findings.append(f)

    def add_code(self, system: str, code: str, description: str) -> None:
        with self._lock:
            self.codes.append({"system": system, "code": code, "description": description})

    def latest_vital(self, name: str) -> VitalReading | None:
        with self._lock:
            for v in reversed(self.vitals):
                if v.name == name:
                    return v
            return None

    def latest_lab(self, name: str) -> LabResult | None:
        with self._lock:
            for lab in reversed(self.labs):
                if lab.name == name:
                    return lab
            return None


class PatientRegistry:
    """In-memory store keyed by ``patient_id`` with optional Storage mirror."""

    def __init__(self, storage: Storage | None = None) -> None:
        self.storage = storage
        self._patients: dict[str, PatientContext] = {}
        self._lock = threading.RLock()
        if storage is not None:
            try:
                for p in storage.list_patients():
                    self._patients[p.patient_id] = p
            except Exception:  # pragma: no cover - defensive
                pass

    def _persist(self, patient: PatientContext) -> None:
        if self.storage is None:
            return
        try:
            self.storage.save_patient(patient)
        except Exception:  # pragma: no cover - defensive
            pass

    def get_or_create(self, patient_id: str, **kwargs: Any) -> PatientContext:
        with self._lock:
            if patient_id not in self._patients:
                self._patients[patient_id] = PatientContext(patient_id=patient_id, **kwargs)
                self._persist(self._patients[patient_id])
            return self._patients[patient_id]

    def get(self, patient_id: str) -> PatientContext | None:
        with self._lock:
            return self._patients.get(patient_id)

    def all(self) -> list[PatientContext]:
        with self._lock:
            return list(self._patients.values())

    def save(self, patient: PatientContext) -> None:
        """Mirror an in-memory mutation to durable storage (if any)."""
        self._persist(patient)

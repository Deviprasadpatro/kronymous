"""Chronic Care Agent — monitors vitals/labs and proposes care-plan adjustments."""

from __future__ import annotations

from typing import Any

from ..core.context import LabResult, PatientContext, VitalReading
from ..data.protocols import (
    CONDITION_RECOMMENDATIONS,
    DEFAULT_KPIS,
    LAB_THRESHOLDS,
    VITAL_THRESHOLDS,
    Threshold,
)
from .base import Agent

_CONDITION_TRIGGERS = {
    "hypertension": ("hypertension", "htn"),
    "diabetes": ("diabetes", "t2dm", "t1dm", "dm"),
    "heart_failure": ("heart failure", "chf"),
    "copd": ("copd",),
    "ckd": ("ckd", "chronic kidney"),
}


class ChronicCareAgent(Agent):
    """Watches incoming data streams against established protocols."""

    name = "chronic_care"

    # ------------------------------------------------------------------
    def run(self, patient: PatientContext) -> dict[str, Any]:
        deviations = self._evaluate_thresholds(patient)
        recs = self._build_recommendations(patient, deviations)
        kpi_deltas = self._kpi_deltas(patient, deviations)

        suggested = {
            "deviations": deviations,
            "recommendations": recs,
            "kpi_deltas": kpi_deltas,
        }

        severity = "notice"
        if any(d["severity"] == "critical" for d in deviations):
            severity = "critical"
        elif any(d["severity"] == "warning" for d in deviations):
            severity = "warning"

        action = self.safety.propose(
            actor=self.name,
            description="Chronic care plan adjustment based on monitored data.",
            rationale=f"{len(deviations)} deviation(s) from protocol thresholds.",
            evidence=[f"{d['metric']}={d['value']} {d['unit']} ({d['direction']} {d['threshold']})" for d in deviations],
            suggested_action=suggested,
            severity=severity,
            patient_id=patient.patient_id,
        )

        for d in deviations:
            self.emit(
                "vitals.deviation" if d["kind"] == "vital" else "labs.deviation",
                d,
                patient_id=patient.patient_id,
                severity=d["severity"],
            )
        self.audit.record(
            actor=self.name,
            action="evaluate",
            patient_id=patient.patient_id,
            detail={"deviations": [d["metric"] for d in deviations], "severity": severity},
        )
        return {"action_id": action.action_id, "suggestion": suggested, "severity": severity}

    # ------------------------------------------------------------------
    def health_check(self, patient: PatientContext | None = None) -> bool:
        from ..core.context import PatientContext as PC
        probe = PC(patient_id="__probe__")
        probe.add_vital(VitalReading(name="systolic_bp", value=120, unit="mmHg"))
        probe.add_vital(VitalReading(name="spo2", value=98, unit="%"))
        out = self._evaluate_thresholds(probe)
        return out == []

    # ------------------------------------------------------------------
    def _evaluate_thresholds(self, patient: PatientContext) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for v in patient.vitals:
            t = VITAL_THRESHOLDS.get(v.name)
            if not t:
                continue
            dev = _check(t, v.value)
            if dev:
                out.append({**dev, "metric": v.name, "value": v.value, "unit": t.unit, "kind": "vital"})
        for lab in patient.labs:
            t = LAB_THRESHOLDS.get(lab.name)
            if not t:
                continue
            dev = _check(t, lab.value)
            if dev:
                out.append({**dev, "metric": lab.name, "value": lab.value, "unit": t.unit, "kind": "lab"})
        return out

    def _build_recommendations(self, patient: PatientContext, deviations: list[dict[str, Any]]) -> list[str]:
        recs: list[str] = []
        seen: set[str] = set()
        text = " ".join(patient.conditions).lower()
        # Condition-driven recs
        for cond_key, triggers in _CONDITION_TRIGGERS.items():
            if any(t in text for t in triggers):
                for r in CONDITION_RECOMMENDATIONS.get(cond_key, []):
                    if r not in seen:
                        recs.append(r)
                        seen.add(r)
        # Allergy guardrail
        if patient.allergies:
            recs.append(
                "Verify all proposed therapies against documented allergies: "
                + ", ".join(patient.allergies)
            )
        # Critical deviation always triggers escalation rec.
        if any(d["severity"] == "critical" for d in deviations):
            recs.insert(0, "Escalate to attending physician immediately for critical deviation.")
        return recs

    def _kpi_deltas(self, patient: PatientContext, deviations: list[dict[str, Any]]) -> dict[str, float]:
        """Project KPI movement (per master-prompt refinement)."""
        baseline = {**DEFAULT_KPIS, **patient.kpis}
        delta: dict[str, float] = {}
        # Crude heuristic: each warning adds 0.1 day to ALOS, each critical adds 0.5.
        alos_bump = sum(0.5 if d["severity"] == "critical" else 0.1 for d in deviations)
        if alos_bump:
            delta["alos_days"] = round(alos_bump, 2)
        # Bed occupancy: criticals slightly raise occupancy projection.
        crit = sum(1 for d in deviations if d["severity"] == "critical")
        if crit:
            delta["bed_occupancy_pct"] = round(crit * 0.4, 2)
        # Readmission risk projection.
        if any("heart_failure" in patient.conditions or "chf" in c.lower() for c in patient.conditions):
            delta["readmission_30d_pct"] = round(len(deviations) * 0.6, 2)
        # Prefix sign for clarity in reports.
        return {k: v for k, v in delta.items() if v != 0 and k in baseline}


def _check(t: Threshold, value: float) -> dict[str, Any] | None:
    if t.high is not None and value > t.high:
        return {"direction": ">", "threshold": t.high, "severity": t.severity_high, "note": t.note}
    if t.low is not None and value < t.low:
        return {"direction": "<", "threshold": t.low, "severity": t.severity_low, "note": t.note}
    return None


__all__ = ["ChronicCareAgent", "VitalReading", "LabResult"]

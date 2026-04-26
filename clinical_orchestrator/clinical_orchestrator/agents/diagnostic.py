"""Diagnostic Agent — synthesizes multimodal sub-agent outputs.

Coordinates the **Imaging**, **Pathology**, and **History** sub-agents and
produces a single structured diagnostic suggestion (differential + severity
+ recommended next steps) routed through the HITL safety gate.
"""

from __future__ import annotations

from typing import Any

from ..core.context import Finding, PatientContext
from .base import Agent
from .subagents.history import HistorySubAgent
from .subagents.imaging import ImagingSubAgent
from .subagents.pathology import PathologySubAgent


class DiagnosticAgent(Agent):
    """Top-level diagnostic coordinator."""

    name = "diagnostic"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.imaging = ImagingSubAgent()
        self.pathology = PathologySubAgent()
        self.history = HistorySubAgent()

    def run(
        self,
        patient: PatientContext,
        imaging_studies: list[dict[str, Any]] | None = None,
        pathology_reports: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        findings: list[Finding] = []
        # History first — its outputs frame everything else.
        findings.extend(self.history.analyze(patient))
        for study in imaging_studies or []:
            findings.extend(self.imaging.analyze(study))
        for report in pathology_reports or []:
            findings.extend(self.pathology.analyze(report))

        # Persist findings on the patient record (cross-collab).
        for f in findings:
            patient.add_finding(f)
            self.emit(
                "diagnostic.finding",
                {
                    "description": f.description,
                    "confidence": f.confidence,
                    "spatial_ref": f.spatial_ref,
                    "source": f.source,
                },
                patient_id=patient.patient_id,
                severity="notice",
            )

        differential, severity = self._summarize(findings)
        suggestion = {
            "findings": [
                {
                    "source": f.source,
                    "description": f.description,
                    "confidence": f.confidence,
                    "spatial_ref": f.spatial_ref,
                    "citations": f.citations,
                }
                for f in findings
            ],
            "differential": differential,
            "next_steps": self._next_steps(findings),
        }
        action = self.safety.propose(
            actor=self.name,
            description="Diagnostic synthesis across imaging, pathology, and history.",
            rationale=f"{len(findings)} structured finding(s) consolidated.",
            evidence=[f.description for f in findings[:5]],
            suggested_action=suggestion,
            severity=severity,
            patient_id=patient.patient_id,
        )
        self.audit.record(
            actor=self.name,
            action="synthesize",
            patient_id=patient.patient_id,
            detail={"finding_count": len(findings), "severity": severity},
        )
        return {"action_id": action.action_id, "suggestion": suggestion, "severity": severity}

    def health_check(self, patient: PatientContext | None = None) -> bool:
        from ..core.context import PatientContext as PC
        probe = PC(patient_id="__probe__", conditions=["hypertension"])
        out = self.history.analyze(probe)
        return any("Active problem list" in f.description for f in out)

    # ------------------------------------------------------------------
    _SEVERITY_RANK = {"info": 0, "notice": 1, "warning": 2, "critical": 3}

    def _summarize(self, findings: list[Finding]) -> tuple[list[str], str]:
        differential: list[str] = []
        severity = "info"

        def bump(level: str) -> None:
            nonlocal severity
            if self._SEVERITY_RANK[level] > self._SEVERITY_RANK[severity]:
                severity = level

        for f in findings:
            d = f.description.lower()
            if "pneumonia" in d or "consolidation" in d:
                differential.append("Community-acquired pneumonia")
                bump("warning")
            if "cardiomegaly" in d or "heart failure" in d:
                differential.append("Decompensated heart failure")
                bump("warning")
            if "carcinoma" in d or "adenocarcinoma" in d:
                differential.append("Malignancy — staging required")
                bump("critical")
            if "tuberculosis" in d or "acid-fast" in d:
                differential.append("Active tuberculosis")
                bump("critical")
        # Dedupe preserving order.
        seen: set[str] = set()
        differential = [d for d in differential if not (d in seen or seen.add(d))]
        return differential, severity

    def _next_steps(self, findings: list[Finding]) -> list[str]:
        steps: list[str] = []
        text = " ".join(f.description.lower() for f in findings)
        if "pneumonia" in text or "consolidation" in text:
            steps.append("Initiate empiric antibiotics per local antibiogram; obtain sputum culture.")
        if "carcinoma" in text:
            steps.append("Refer to oncology; order staging CT chest/abdomen/pelvis and PET if indicated.")
        if "acid-fast" in text:
            steps.append("Place patient on airborne isolation; notify infection prevention.")
        if "cardiomegaly" in text or "heart failure" in text:
            steps.append("Order BNP/NT-proBNP and echocardiogram; review GDMT.")
        if not steps:
            steps.append("Continue routine monitoring; no acute interventions required at this time.")
        return steps

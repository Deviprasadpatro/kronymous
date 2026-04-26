"""Top-level Clinical Orchestrator (Supervisor agent).

Wires together the event bus, shared patient registry, safety gate, audit
log, self-debugger, and the three operational modules (Documentation,
Chronic Care, Diagnostic). It is also responsible for the
*cross-collaboration framework*: subscribing each module to the events
emitted by the others so findings propagate automatically.
"""

from __future__ import annotations

from typing import Any

from ..agents.chronic_care import ChronicCareAgent
from ..agents.diagnostic import DiagnosticAgent
from ..agents.documentation import DocumentationAgent
from .audit import AuditLog
from .context import PatientContext, PatientRegistry
from .event_bus import ClinicalEvent, EventBus
from .llm import LLMProvider
from .safety import PendingAction, SafetyGate
from .self_debug import SelfDebugger


class ClinicalOrchestrator:
    """Top-level supervisor that coordinates all agents."""

    def __init__(
        self,
        bus: EventBus | None = None,
        safety: SafetyGate | None = None,
        audit: AuditLog | None = None,
        llm: LLMProvider | None = None,
        debugger: SelfDebugger | None = None,
    ) -> None:
        self.bus = bus or EventBus()
        self.safety = safety or SafetyGate()
        self.audit = audit or AuditLog()
        self.llm = llm or LLMProvider()
        self.debugger = debugger or SelfDebugger()
        self.registry = PatientRegistry()

        self.documentation = DocumentationAgent(self.bus, self.safety, self.audit, self.llm)
        self.chronic_care = ChronicCareAgent(self.bus, self.safety, self.audit, self.llm)
        self.diagnostic = DiagnosticAgent(self.bus, self.safety, self.audit, self.llm)

        self._wire_cross_collaboration()

    # ------------------------------------------------------------------
    # Cross-collaboration: agents listen to each other's events
    # ------------------------------------------------------------------
    def _wire_cross_collaboration(self) -> None:
        # Diagnostic → Documentation: append new findings to the SOAP draft.
        self.bus.subscribe("diagnostic.finding", self._on_diagnostic_finding)
        # Diagnostic → Chronic Care: re-run risk stratification.
        self.bus.subscribe("diagnostic.finding", self._on_finding_for_chronic)
        # Chronic-care critical deviations → trigger a fresh diagnostic synthesis.
        self.bus.subscribe("vitals.deviation", self._on_critical_deviation)
        self.bus.subscribe("labs.deviation", self._on_critical_deviation)
        # Internal handler errors → record audit entry.
        self.bus.subscribe("system.handler_error", self._on_handler_error)

    # ------------------------------------------------------------------
    def _on_diagnostic_finding(self, event: ClinicalEvent) -> None:
        if not event.patient_id:
            return
        patient = self.registry.get(event.patient_id)
        if not patient:
            return
        desc = event.payload.get("description", "")
        if desc:
            self.documentation.apply_finding(patient, desc)

    def _on_finding_for_chronic(self, event: ClinicalEvent) -> None:
        if not event.patient_id:
            return
        patient = self.registry.get(event.patient_id)
        if not patient:
            return
        # Avoid recursive emission storms: only re-evaluate if there's data.
        if patient.vitals or patient.labs:
            try:
                self.debugger.call("chronic_care", self.chronic_care.run, patient)
            except Exception as exc:
                self.audit.record(
                    actor="orchestrator",
                    action="chronic_care_recheck_failed",
                    detail={"error": str(exc)},
                    patient_id=patient.patient_id,
                )

    def _on_critical_deviation(self, event: ClinicalEvent) -> None:
        if event.severity != "critical" or not event.patient_id:
            return
        self.audit.record(
            actor="orchestrator",
            action="critical_deviation_escalated",
            detail=event.payload,
            patient_id=event.patient_id,
        )

    def _on_handler_error(self, event: ClinicalEvent) -> None:
        self.audit.record(
            actor="orchestrator",
            action="handler_error",
            detail=event.payload,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def upsert_patient(self, patient_id: str, **fields: Any) -> PatientContext:
        patient = self.registry.get_or_create(patient_id, **{k: v for k, v in fields.items() if v is not None})
        for k, v in fields.items():
            if v is None:
                continue
            if hasattr(patient, k):
                setattr(patient, k, v)
        return patient

    def ingest_transcript(self, patient_id: str, transcript: str) -> dict[str, Any]:
        patient = self.registry.get_or_create(patient_id)
        return self.debugger.call("documentation", self.documentation.run, transcript, patient)

    def ingest_vitals(self, patient_id: str, vitals: list[dict[str, Any]]) -> dict[str, Any]:
        from .context import VitalReading
        patient = self.registry.get_or_create(patient_id)
        for v in vitals:
            patient.add_vital(VitalReading(name=v["name"], value=float(v["value"]), unit=v.get("unit", "")))
        return self.debugger.call("chronic_care", self.chronic_care.run, patient)

    def ingest_labs(self, patient_id: str, labs: list[dict[str, Any]]) -> dict[str, Any]:
        from .context import LabResult
        patient = self.registry.get_or_create(patient_id)
        for lab in labs:
            patient.add_lab(LabResult(
                name=lab["name"], value=float(lab["value"]), unit=lab.get("unit", ""),
                reference_low=lab.get("reference_low"), reference_high=lab.get("reference_high"),
            ))
        return self.debugger.call("chronic_care", self.chronic_care.run, patient)

    def diagnose(
        self,
        patient_id: str,
        imaging_studies: list[dict[str, Any]] | None = None,
        pathology_reports: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        patient = self.registry.get_or_create(patient_id)
        return self.debugger.call(
            "diagnostic",
            self.diagnostic.run,
            patient,
            imaging_studies=imaging_studies,
            pathology_reports=pathology_reports,
        )

    # -- HITL ------------------------------------------------------------
    def pending_reviews(self, patient_id: str | None = None) -> list[PendingAction]:
        return self.safety.pending(patient_id=patient_id)

    def confirm(self, action_id: str, reviewer: str) -> PendingAction:
        action = self.safety.confirm(action_id, reviewer)
        self._apply_confirmed(action)
        self.audit.record(actor="reviewer", action="confirm", patient_id=action.patient_id,
                          detail={"action_id": action_id, "reviewer": reviewer})
        return action

    def modify(self, action_id: str, reviewer: str, final_action: dict[str, Any]) -> PendingAction:
        action = self.safety.modify(action_id, reviewer, final_action)
        self._apply_confirmed(action)
        self.audit.record(actor="reviewer", action="modify", patient_id=action.patient_id,
                          detail={"action_id": action_id, "reviewer": reviewer})
        return action

    def reject(self, action_id: str, reviewer: str) -> PendingAction:
        action = self.safety.reject(action_id, reviewer)
        self.audit.record(actor="reviewer", action="reject", patient_id=action.patient_id,
                          detail={"action_id": action_id, "reviewer": reviewer})
        return action

    # ------------------------------------------------------------------
    def _apply_confirmed(self, action: PendingAction) -> None:
        """Commit a confirmed/modified suggestion to the patient record."""
        if not action.patient_id:
            return
        patient = self.registry.get(action.patient_id)
        if not patient:
            return
        # NB: explicit `is None` check — an empty-dict modification (`{}`) means
        # "the reviewer cleared every field" and must not silently fall back to
        # the original suggestion. Truthiness check would re-commit it.
        payload = action.final_action if action.final_action is not None else action.suggested_action
        if action.actor == "documentation":
            soap = payload.get("soap", {})
            if isinstance(soap, dict):
                patient.soap_note.update({k: str(v) for k, v in soap.items()})
            for entry in payload.get("icd10", []):
                patient.add_code("ICD-10", entry["code"], entry["description"])
            for entry in payload.get("cpt", []):
                patient.add_code("CPT", entry["code"], entry["description"])
        elif action.actor == "chronic_care":
            for rec in payload.get("recommendations", []):
                if rec not in patient.care_plan:
                    patient.care_plan.append(rec)
            for k, v in payload.get("kpi_deltas", {}).items():
                patient.kpis[k] = patient.kpis.get(k, 0.0) + float(v)
        elif action.actor == "diagnostic":
            for step in payload.get("next_steps", []):
                if step not in patient.care_plan:
                    patient.care_plan.append(step)

    # -- Health ----------------------------------------------------------
    def health(self) -> dict[str, Any]:
        agent_health = {
            "documentation": self.documentation.health_check(),
            "chronic_care": self.chronic_care.health_check(),
            "diagnostic": self.diagnostic.health_check(),
        }
        return {
            "ok": all(agent_health.values()),
            "agents": agent_health,
            "circuits": self.debugger.health(),
            "patients": len(self.registry.all()),
            "pending_reviews": len(self.safety.pending()),
            "events_seen": len(self.bus.history()),
        }

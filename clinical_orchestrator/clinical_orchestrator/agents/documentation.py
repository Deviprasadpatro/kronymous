"""Documentation Agent — turns clinician-patient dialogue into a SOAP note.

The agent runs in two modes:

* **LLM mode** (when ``OPENAI_API_KEY`` is set): asks the LLM to produce a
  structured SOAP note as JSON.
* **Rule-based mode** (default, used in tests / offline): heuristically
  segments the transcript into S/O/A/P sections and extracts ICD-10 / CPT
  codes via keyword search.

Both modes go through the HITL safety gate before anything is committed to
the patient's record.
"""

from __future__ import annotations

import json
import re
from typing import Any

from ..core.context import PatientContext
from ..core.pii import mask
from ..data.icd10_cpt import CPT, ICD10, search
from .base import Agent

_SECTION_HEADERS = {
    "s": "subjective",
    "subjective": "subjective",
    "o": "objective",
    "objective": "objective",
    "a": "assessment",
    "assessment": "assessment",
    "p": "plan",
    "plan": "plan",
}


class DocumentationAgent(Agent):
    """Generates SOAP notes + ICD-10/CPT codes from encounter text."""

    name = "documentation"

    def run(self, transcript: str, patient: PatientContext) -> dict[str, Any]:
        soap = self._llm_soap(transcript) or self._rule_based_soap(transcript)
        codes_icd = search(ICD10, transcript)
        codes_cpt = search(CPT, transcript)

        # Apply contextual awareness: if the patient already carries a
        # condition mentioned in the SOAP note, ensure the related ICD-10
        # code is included.
        for cond in patient.conditions:
            for entry in search(ICD10, cond):
                if entry["code"] not in {c["code"] for c in codes_icd}:
                    codes_icd.append(entry)

        suggestion = {
            "soap": soap,
            "icd10": codes_icd,
            "cpt": codes_cpt,
        }

        self.audit.record(
            actor=self.name,
            action="propose_soap",
            patient_id=patient.patient_id,
            detail={"icd10": [c["code"] for c in codes_icd],
                    "cpt": [c["code"] for c in codes_cpt]},
        )
        action = self.safety.propose(
            actor=self.name,
            description="Proposed SOAP note + coded findings for current encounter.",
            rationale="Derived from encounter transcript and patient history.",
            evidence=[mask(transcript[:280])],
            suggested_action=suggestion,
            severity="notice",
            patient_id=patient.patient_id,
        )

        self.emit(
            "documentation.draft",
            {"action_id": action.action_id, "summary": soap.get("assessment", "")},
            patient_id=patient.patient_id,
        )
        return {"action_id": action.action_id, "draft": suggestion}

    # ------------------------------------------------------------------
    def apply_finding(self, patient: PatientContext, finding: str) -> None:
        """Cross-collab hook: append a new finding to the active SOAP note draft."""
        existing = patient.soap_note.get("assessment", "")
        patient.soap_note["assessment"] = (existing + "\n- " + finding).strip()
        self.audit.record(
            actor=self.name,
            action="append_finding",
            patient_id=patient.patient_id,
            detail={"finding": mask(finding)},
        )

    def health_check(self, patient: PatientContext | None = None) -> bool:
        sample = "Patient reports headache. BP 150/95. Continue lisinopril."
        soap = self._rule_based_soap(sample)
        return all(k in soap for k in ("subjective", "objective", "assessment", "plan"))

    # ------------------------------------------------------------------
    # LLM path (best-effort; returns None on any failure → fallback used)
    # ------------------------------------------------------------------
    def _llm_soap(self, transcript: str) -> dict[str, str] | None:
        if not self.llm.available:
            return None
        system = (
            "You are a clinical scribe. Produce a SOAP note as strict JSON with "
            "keys: subjective, objective, assessment, plan. No prose, no markdown."
        )
        out = self.llm.complete(system=system, user=transcript)
        if not out:
            return None
        try:
            data = json.loads(out)
            if not all(k in data for k in ("subjective", "objective", "assessment", "plan")):
                return None
            return {k: str(data[k]) for k in ("subjective", "objective", "assessment", "plan")}
        except (json.JSONDecodeError, TypeError):
            return None

    # ------------------------------------------------------------------
    # Rule-based fallback
    # ------------------------------------------------------------------
    def _rule_based_soap(self, transcript: str) -> dict[str, str]:
        sections = {"subjective": [], "objective": [], "assessment": [], "plan": []}
        current = "subjective"

        # Try to honor explicit S:/O:/A:/P: markers if present.
        for raw_line in transcript.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            m = re.match(r"^([A-Za-z]+)\s*[:\-]\s*(.*)$", line)
            if m and m.group(1).lower() in _SECTION_HEADERS:
                current = _SECTION_HEADERS[m.group(1).lower()]
                rest = m.group(2).strip()
                if rest:
                    sections[current].append(rest)
                continue
            sections[current].append(line)

        # If everything ended up in 'subjective' (no markers), do heuristic split.
        if not any(sections[k] for k in ("objective", "assessment", "plan")):
            text = " ".join(sections["subjective"])
            sections = self._heuristic_split(text)

        return {k: " ".join(v).strip() for k, v in sections.items()}

    def _heuristic_split(self, text: str) -> dict[str, list[str]]:
        sentences = re.split(r"(?<=[.!?])\s+", text)
        out: dict[str, list[str]] = {"subjective": [], "objective": [], "assessment": [], "plan": []}
        objective_kws = ("bp", "blood pressure", "hr", "heart rate", "temp", "spo2", "exam",
                         "auscultation", "rhonchi", "rales", "weight", "labs", "ecg", "ekg",
                         "x-ray", "imaging", "ct ", "mri ")
        plan_kws = ("plan", "continue", "start", "discontinue", "increase", "decrease",
                    "schedule", "follow up", "follow-up", "refer", "order")
        assessment_kws = ("likely", "consistent with", "diagnosis", "impression", "rule out",
                          "suggests", "differential")
        for s in sentences:
            sl = s.lower()
            if any(k in sl for k in plan_kws):
                out["plan"].append(s)
            elif any(k in sl for k in assessment_kws):
                out["assessment"].append(s)
            elif any(k in sl for k in objective_kws):
                out["objective"].append(s)
            else:
                out["subjective"].append(s)
        return out

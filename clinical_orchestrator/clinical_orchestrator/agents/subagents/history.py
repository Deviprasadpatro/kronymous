"""History sub-agent.

Synthesizes the longitudinal patient record (problem list, medications,
allergies, prior encounters) into structured findings the diagnostic agent
can use to refine its differential.
"""

from __future__ import annotations

from ...core.context import Finding, PatientContext


class HistorySubAgent:
    name = "history"

    def analyze(self, patient: PatientContext) -> list[Finding]:
        out: list[Finding] = []
        if patient.allergies:
            out.append(
                Finding(
                    source=self.name,
                    description="Documented allergies: " + ", ".join(patient.allergies),
                    confidence=1.0,
                )
            )
        if patient.conditions:
            out.append(
                Finding(
                    source=self.name,
                    description="Active problem list: " + ", ".join(patient.conditions),
                    confidence=1.0,
                )
            )
        if patient.medications:
            out.append(
                Finding(
                    source=self.name,
                    description="Current medications: " + ", ".join(patient.medications),
                    confidence=1.0,
                )
            )
        return out

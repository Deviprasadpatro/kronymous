"""Pathology sub-agent.

Accepts a structured pathology report and surfaces clinically actionable
findings (malignancy markers, grading, infection signals).
"""

from __future__ import annotations

from typing import Any

from ...core.context import Finding


class PathologySubAgent:
    name = "pathology"

    KEYWORD_RULES: list[tuple[str, str, float]] = [
        ("invasive ductal carcinoma", "Invasive ductal carcinoma identified — oncology referral indicated.", 0.92),
        ("adenocarcinoma", "Adenocarcinoma on biopsy — recommend staging workup.", 0.9),
        ("dysplasia", "Dysplastic changes noted — recommend surveillance interval review.", 0.7),
        ("gram-positive cocci", "Gram-positive cocci on culture — narrow antibiotics per sensitivities.", 0.8),
        ("gram-negative", "Gram-negative organism — review antibiotic coverage and source control.", 0.8),
        ("acid-fast", "Acid-fast bacilli detected — initiate TB precautions and infectious-disease consult.", 0.95),
        ("benign", "Benign histology — routine follow-up.", 0.6),
    ]

    def analyze(self, report: dict[str, Any]) -> list[Finding]:
        text = (report.get("text") or "").lower()
        out: list[Finding] = []
        for kw, desc, conf in self.KEYWORD_RULES:
            if kw in text:
                out.append(
                    Finding(
                        source=self.name,
                        description=desc,
                        confidence=conf,
                        citations=[f"Pathology report {report.get('report_id', '')}".strip()],
                    )
                )
        return out

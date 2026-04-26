"""Imaging sub-agent.

Stand-in for an actual imaging model. It accepts a structured *imaging
study* descriptor — modality, anatomical region, and an optional list of
pre-extracted features (or pixel statistics) — and returns findings with
spatial references (bounding boxes / heatmap region IDs).

In production this would wrap a CV model (e.g. RSNA chest X-ray classifier,
nnU-Net segmentation, etc.); here we give a deterministic implementation so
the orchestrator can be tested end-to-end offline.
"""

from __future__ import annotations

from typing import Any

from ...core.context import Finding


class ImagingSubAgent:
    name = "imaging"

    KNOWN_PATTERNS = {
        # feature_keyword -> (description, default bbox, citation)
        "consolidation": (
            "Right lower lobe airspace consolidation, suspicious for pneumonia.",
            {"image_id": None, "bbox": [320, 410, 470, 560], "view": "PA"},
            "Fleischner Society 2017 — pneumonia patterns.",
        ),
        "cardiomegaly": (
            "Cardiothoracic ratio >0.5 — cardiomegaly.",
            {"image_id": None, "bbox": [280, 350, 760, 690], "view": "PA"},
            "ACR Appropriateness Criteria — Heart Failure.",
        ),
        "pleural effusion": (
            "Blunting of costophrenic angle, suspicious for pleural effusion.",
            {"image_id": None, "bbox": [620, 600, 880, 820], "view": "PA"},
            "Fleischner Society — pleural effusion.",
        ),
        "ground glass": (
            "Bilateral peripheral ground-glass opacities.",
            {"image_id": None, "bbox": [120, 200, 880, 700], "view": "axial"},
            "RSNA viral pneumonia patterns.",
        ),
        "nodule": (
            "Solitary pulmonary nodule, recommend follow-up CT per Fleischner guidelines.",
            {"image_id": None, "bbox": [500, 320, 560, 380], "view": "PA"},
            "Fleischner Society pulmonary nodule guidelines (2017).",
        ),
    }

    def analyze(self, study: dict[str, Any]) -> list[Finding]:
        features = [f.lower() for f in study.get("features", [])]
        out: list[Finding] = []
        image_id = study.get("image_id", "img-unknown")
        for kw, (desc, bbox, citation) in self.KNOWN_PATTERNS.items():
            if any(kw in f for f in features):
                ref = dict(bbox)
                ref["image_id"] = image_id
                out.append(
                    Finding(
                        source=self.name,
                        description=desc,
                        confidence=0.78,
                        spatial_ref=ref,
                        citations=[citation],
                    )
                )
        if not out and study.get("modality"):
            out.append(
                Finding(
                    source=self.name,
                    description=f"No acute findings on {study['modality']}.",
                    confidence=0.5,
                    spatial_ref={"image_id": image_id},
                )
            )
        return out

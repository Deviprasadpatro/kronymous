"""Clinical protocols / guidelines used by the Chronic Care Agent.

These are *illustrative* thresholds drawn from common public guidelines (e.g.
JNC-8 for hypertension, ADA for diabetes). They are intentionally simple and
must be reviewed by clinicians before any production use — every action they
trigger goes through the HITL safety gate.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Threshold:
    metric: str
    low: float | None = None
    high: float | None = None
    unit: str = ""
    severity_high: str = "warning"
    severity_low: str = "warning"
    note: str = ""


# Vitals thresholds.
VITAL_THRESHOLDS: dict[str, Threshold] = {
    "systolic_bp": Threshold("systolic_bp", low=90, high=140, unit="mmHg",
                             severity_high="warning", severity_low="warning",
                             note="JNC-8 target <140 mmHg for most adults; <130 if high CV risk."),
    "diastolic_bp": Threshold("diastolic_bp", low=60, high=90, unit="mmHg",
                              severity_high="warning", severity_low="notice"),
    "heart_rate": Threshold("heart_rate", low=50, high=110, unit="bpm",
                            severity_high="notice", severity_low="notice"),
    "spo2": Threshold("spo2", low=92, high=None, unit="%",
                      severity_low="critical", note="Hypoxemia threshold."),
    "temperature": Threshold("temperature", low=35.5, high=38.0, unit="C",
                             severity_high="warning"),
    "respiratory_rate": Threshold("respiratory_rate", low=10, high=24, unit="/min"),
}

# Lab thresholds.
LAB_THRESHOLDS: dict[str, Threshold] = {
    "glucose": Threshold("glucose", low=70, high=180, unit="mg/dL",
                         severity_high="warning", severity_low="critical",
                         note="ADA in-hospital target 140-180 mg/dL."),
    "hba1c": Threshold("hba1c", low=None, high=7.0, unit="%",
                       severity_high="warning", note="ADA general target <7%."),
    "potassium": Threshold("potassium", low=3.5, high=5.5, unit="mEq/L",
                           severity_high="critical", severity_low="critical"),
    "creatinine": Threshold("creatinine", low=None, high=1.3, unit="mg/dL",
                            severity_high="warning", note="Watch for AKI / CKD progression."),
    "bnp": Threshold("bnp", low=None, high=400, unit="pg/mL",
                     severity_high="warning", note="Suggests heart failure decompensation."),
}


# Per-condition recommendations triggered when thresholds are breached.
CONDITION_RECOMMENDATIONS: dict[str, list[str]] = {
    "hypertension": [
        "Reinforce DASH diet, sodium <2g/day, weight management.",
        "Verify medication adherence; consider titrating ACEi/ARB or thiazide.",
        "Schedule home BP monitoring with 7-day average review.",
    ],
    "diabetes": [
        "Review CGM / fingerstick logs; reinforce carb counting.",
        "Consider basal insulin or GLP-1 RA titration if A1c >7%.",
        "Order annual retinopathy and diabetic foot exam if overdue.",
    ],
    "heart_failure": [
        "Assess weight trend (>2 lb/day or 5 lb/week → call clinic).",
        "Verify guideline-directed therapy: ACEi/ARNI + beta-blocker + MRA + SGLT2i.",
        "Review fluid/sodium restriction adherence.",
    ],
    "copd": [
        "Confirm inhaler technique; consider LAMA/LABA add-on.",
        "Reinforce smoking cessation and pulmonary rehab.",
        "Update vaccinations (influenza, pneumococcal, COVID).",
    ],
    "ckd": [
        "Avoid nephrotoxins (NSAIDs, contrast unless essential).",
        "Optimize BP <130/80 with ACEi/ARB.",
        "Consider SGLT2i if eGFR ≥20 and proteinuric.",
    ],
}


# KPIs the chronic care agent watches (per master prompt: ALOS, bed occupancy).
DEFAULT_KPIS = {
    "alos_days": 4.2,            # average length of stay (days)
    "bed_occupancy_pct": 78.0,   # % of staffed beds occupied
    "readmission_30d_pct": 12.0,
}

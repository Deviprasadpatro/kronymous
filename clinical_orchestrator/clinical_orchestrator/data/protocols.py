"""Clinical protocols / guidelines used by the Chronic Care Agent.

Thresholds and recommendations below are pinned to specific publicly cited
guideline versions (see :data:`PROTOCOL_CITATIONS`). They are deliberately
**conservative defaults** suitable for triage / decision support and **must**
be reviewed by clinicians and tuned to local formulary and population before
clinical use. Every action they trigger goes through the HITL safety gate.
"""

from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Protocol provenance
# ---------------------------------------------------------------------------
PROTOCOL_VERSION = "v0.2.0"
PROTOCOL_CITATIONS = {
    "hypertension": [
        "JNC-8: James PA et al., 2014 Evidence-Based Guideline for the Management of "
        "High Blood Pressure in Adults. JAMA. 2014;311(5):507–520.",
        "ACC/AHA 2017 Guideline for the Prevention, Detection, Evaluation, and "
        "Management of High Blood Pressure in Adults.",
    ],
    "diabetes": [
        "ADA Standards of Care in Diabetes — 2024 (Diabetes Care, vol. 47, supplement 1).",
    ],
    "heart_failure": [
        "AHA/ACC/HFSA 2022 Guideline for the Management of Heart Failure (Heidenreich PA et al., 2022).",
    ],
    "copd": [
        "GOLD 2024 Report — Global Strategy for the Diagnosis, Management, and Prevention of COPD.",
    ],
    "ckd": [
        "KDIGO 2024 Clinical Practice Guideline for the Evaluation and Management of CKD.",
    ],
    "vitals_oxygenation": [
        "BTS 2017 Guideline for Oxygen Use in Healthcare and Emergency Settings (target SpO2 94–98%, "
        "or 88–92% for patients at risk of hypercapnic respiratory failure).",
    ],
    "lab_potassium": [
        "AACE/ACE 2017 Clinical Practice Guidelines for the Diagnosis and Management of Dyslipidemia "
        "and Prevention of Cardiovascular Disease — adult reference 3.5–5.0 mEq/L.",
    ],
}


@dataclass
class Threshold:
    metric: str
    low: float | None = None
    high: float | None = None
    unit: str = ""
    severity_high: str = "warning"
    severity_low: str = "warning"
    note: str = ""
    citation: str = ""


# Vitals thresholds (adult; pediatric / pregnant overrides not modeled here).
VITAL_THRESHOLDS: dict[str, Threshold] = {
    "systolic_bp": Threshold(
        "systolic_bp", low=90, high=140, unit="mmHg",
        severity_high="warning", severity_low="warning",
        note="JNC-8 target <140 mmHg for most adults; ACC/AHA 2017 lowers to <130 if high CV risk.",
        citation="JNC-8 / ACC-AHA 2017",
    ),
    "diastolic_bp": Threshold(
        "diastolic_bp", low=60, high=90, unit="mmHg",
        severity_high="warning", severity_low="notice",
        citation="JNC-8 / ACC-AHA 2017",
    ),
    "heart_rate": Threshold(
        "heart_rate", low=50, high=110, unit="bpm",
        severity_high="notice", severity_low="notice",
        citation="Resting adult sinus reference range",
    ),
    "spo2": Threshold(
        "spo2", low=92, high=None, unit="%",
        severity_low="critical",
        note="BTS 2017: target 94–98%; <92% triggers escalation in non-hypercapnic patients.",
        citation="BTS 2017",
    ),
    "temperature": Threshold(
        "temperature", low=35.5, high=38.0, unit="C",
        severity_high="warning", severity_low="warning",
        citation="WHO adult fever / hypothermia thresholds",
    ),
    "respiratory_rate": Threshold(
        "respiratory_rate", low=10, high=24, unit="/min",
        citation="NEWS2 (RCP UK 2017)",
    ),
}

# Lab thresholds.
LAB_THRESHOLDS: dict[str, Threshold] = {
    "glucose": Threshold(
        "glucose", low=70, high=180, unit="mg/dL",
        severity_high="warning", severity_low="critical",
        note="ADA 2024 inpatient target 140–180 mg/dL; <70 = hypoglycemia.",
        citation="ADA 2024 §16",
    ),
    "hba1c": Threshold(
        "hba1c", low=None, high=7.0, unit="%",
        severity_high="warning",
        note="ADA 2024 general target <7%; individualize for elderly / comorbid.",
        citation="ADA 2024 §6",
    ),
    "potassium": Threshold(
        "potassium", low=3.5, high=5.5, unit="mEq/L",
        severity_high="critical", severity_low="critical",
        citation="Reference 3.5–5.0 mEq/L; outside is critical for arrhythmia risk",
    ),
    "creatinine": Threshold(
        "creatinine", low=None, high=1.3, unit="mg/dL",
        severity_high="warning",
        note="Watch for AKI / CKD progression — interpret with eGFR.",
        citation="KDIGO 2024",
    ),
    "bnp": Threshold(
        "bnp", low=None, high=400, unit="pg/mL",
        severity_high="warning",
        note=">400 suggests heart-failure decompensation; >900 in age >75 (HFA-ESC).",
        citation="AHA/ACC/HFSA 2022",
    ),
    "egfr": Threshold(
        "egfr", low=60, high=None, unit="mL/min/1.73m^2",
        severity_low="warning",
        note="<60 sustained ≥3 months → CKD stage ≥3 (KDIGO 2024).",
        citation="KDIGO 2024",
    ),
    "ldl": Threshold(
        "ldl", low=None, high=100, unit="mg/dL",
        severity_high="notice",
        note="Target <70 mg/dL for ASCVD secondary prevention (AHA/ACC 2018).",
        citation="AHA/ACC 2018 Cholesterol Guideline",
    ),
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


def protocol_versions() -> dict[str, object]:
    """Return a structured snapshot of which guideline versions back the rules."""
    return {
        "protocol_version": PROTOCOL_VERSION,
        "citations": PROTOCOL_CITATIONS,
        "vital_metrics": list(VITAL_THRESHOLDS.keys()),
        "lab_metrics": list(LAB_THRESHOLDS.keys()),
        "tracked_conditions": list(CONDITION_RECOMMENDATIONS.keys()),
    }

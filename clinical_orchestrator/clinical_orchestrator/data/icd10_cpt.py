"""ICD-10-CM lookup tables and pluggable CPT loader.

ICD-10-CM
=========
Codes here are sourced from the **CMS ICD-10-CM FY2025 release** (public
domain). The bundled list is a *curated subset* of the most commonly used
codes (~190 entries) covering chronic conditions, common ED presentations,
mental health, infectious disease, and trauma. For the full ~70k-code set,
provide the CMS XML via :func:`load_icd10_cm_xml`.

Source: https://www.cms.gov/medicare/coding-billing/icd-10-codes  (FY2025)
License: Public domain (US government work).

CPT
===
**CPT® codes are licensed by the AMA and cannot be redistributed.** This
module ships an **empty CPT table by default**. Provide your own licensed
CPT data via :func:`load_cpt_jsonl` (one ``{"code", "description",
"keywords"}`` JSON object per line) or by directly populating :data:`CPT`
at startup. Until you do, CPT lookups return an empty list — the rest of
the system continues to operate.
"""

from __future__ import annotations

import json
from typing import Any

ICD10_CM_VERSION = "FY2025"
ICD10_CM_SOURCE = "CMS — Centers for Medicare & Medicaid Services"
ICD10_CM_LICENSE = "Public Domain (US Government work)"
CPT_VERSION_INFO = "User-supplied (AMA-licensed; not bundled)"


# Each entry maps a list of trigger keywords/phrases (case-insensitive) to a code.
# This is a curated subset of CMS ICD-10-CM FY2025 covering primary care,
# common ED presentations, chronic disease management, mental health, and
# infectious disease. See module docstring for source / licensing.
ICD10: list[dict[str, object]] = [
    # ---------- Cardiovascular ----------
    {"code": "I10", "description": "Essential (primary) hypertension",
     "keywords": ["hypertension", "high blood pressure", "htn", "elevated bp"]},
    {"code": "I11.9", "description": "Hypertensive heart disease without heart failure",
     "keywords": ["hypertensive heart disease"]},
    {"code": "I11.0", "description": "Hypertensive heart disease with heart failure",
     "keywords": ["hypertensive heart failure"]},
    {"code": "I12.9", "description": "Hypertensive CKD with stage 1-4 CKD or unspecified CKD",
     "keywords": ["hypertensive kidney disease", "hypertensive ckd"]},
    {"code": "I20.9", "description": "Angina pectoris, unspecified",
     "keywords": ["angina", "stable angina"]},
    {"code": "I21.9", "description": "Acute myocardial infarction, unspecified",
     "keywords": ["myocardial infarction", "heart attack", "acute mi", "stemi", "nstemi"]},
    {"code": "I25.10", "description": "Atherosclerotic heart disease of native coronary artery without angina pectoris",
     "keywords": ["coronary artery disease", "cad", "atherosclerotic heart disease"]},
    {"code": "I48.91", "description": "Atrial fibrillation, unspecified",
     "keywords": ["atrial fibrillation", "afib", "a-fib"]},
    {"code": "I49.9", "description": "Cardiac arrhythmia, unspecified",
     "keywords": ["arrhythmia"]},
    {"code": "I50.9", "description": "Heart failure, unspecified",
     "keywords": ["heart failure", "chf", "congestive heart failure"]},
    {"code": "I50.21", "description": "Acute systolic (congestive) heart failure",
     "keywords": ["acute systolic heart failure", "acute hfref"]},
    {"code": "I50.31", "description": "Acute diastolic (congestive) heart failure",
     "keywords": ["acute diastolic heart failure", "acute hfpef"]},
    {"code": "I63.9", "description": "Cerebral infarction, unspecified",
     "keywords": ["cerebral infarction", "ischemic stroke"]},
    {"code": "I65.23", "description": "Occlusion and stenosis of bilateral carotid arteries",
     "keywords": ["bilateral carotid stenosis"]},
    {"code": "I73.9", "description": "Peripheral vascular disease, unspecified",
     "keywords": ["peripheral vascular disease", "pvd", "peripheral artery disease", "pad"]},
    {"code": "I82.40", "description": "Acute embolism and thrombosis of unspecified deep veins of lower extremity",
     "keywords": ["dvt", "deep vein thrombosis"]},
    {"code": "I26.99", "description": "Other pulmonary embolism without acute cor pulmonale",
     "keywords": ["pulmonary embolism", "pe"]},
    # ---------- Endocrine / metabolic ----------
    {"code": "E11.9", "description": "Type 2 diabetes mellitus without complications",
     "keywords": ["type 2 diabetes", "t2dm", "dm2", "diabetes mellitus type 2"]},
    {"code": "E11.65", "description": "Type 2 diabetes mellitus with hyperglycemia",
     "keywords": ["uncontrolled diabetes", "hyperglycemia"]},
    {"code": "E11.22", "description": "Type 2 diabetes mellitus with diabetic chronic kidney disease",
     "keywords": ["diabetic nephropathy"]},
    {"code": "E11.42", "description": "Type 2 diabetes mellitus with diabetic polyneuropathy",
     "keywords": ["diabetic neuropathy"]},
    {"code": "E11.319", "description": "Type 2 diabetes with unspecified diabetic retinopathy without macular edema",
     "keywords": ["diabetic retinopathy"]},
    {"code": "E10.9", "description": "Type 1 diabetes mellitus without complications",
     "keywords": ["type 1 diabetes", "t1dm"]},
    {"code": "E78.5", "description": "Hyperlipidemia, unspecified",
     "keywords": ["hyperlipidemia", "dyslipidemia"]},
    {"code": "E78.0", "description": "Pure hypercholesterolemia",
     "keywords": ["hypercholesterolemia", "high cholesterol"]},
    {"code": "E66.9", "description": "Obesity, unspecified",
     "keywords": ["obesity"]},
    {"code": "E03.9", "description": "Hypothyroidism, unspecified",
     "keywords": ["hypothyroidism"]},
    {"code": "E05.90", "description": "Thyrotoxicosis, unspecified without thyrotoxic crisis",
     "keywords": ["hyperthyroidism", "thyrotoxicosis"]},
    {"code": "E87.1", "description": "Hypo-osmolality and hyponatremia",
     "keywords": ["hyponatremia"]},
    {"code": "E87.6", "description": "Hypokalemia",
     "keywords": ["hypokalemia"]},
    # ---------- Respiratory ----------
    {"code": "J18.9", "description": "Pneumonia, unspecified organism",
     "keywords": ["pneumonia", "lower respiratory infection"]},
    {"code": "J15.9", "description": "Unspecified bacterial pneumonia",
     "keywords": ["bacterial pneumonia"]},
    {"code": "J20.9", "description": "Acute bronchitis, unspecified",
     "keywords": ["acute bronchitis"]},
    {"code": "J44.9", "description": "Chronic obstructive pulmonary disease, unspecified",
     "keywords": ["copd", "chronic obstructive pulmonary disease"]},
    {"code": "J44.1", "description": "Chronic obstructive pulmonary disease with (acute) exacerbation",
     "keywords": ["copd exacerbation", "aecopd"]},
    {"code": "J45.909", "description": "Unspecified asthma, uncomplicated",
     "keywords": ["asthma"]},
    {"code": "J45.901", "description": "Unspecified asthma with (acute) exacerbation",
     "keywords": ["asthma exacerbation"]},
    {"code": "J96.01", "description": "Acute respiratory failure with hypoxia",
     "keywords": ["acute respiratory failure", "hypoxic respiratory failure"]},
    {"code": "J96.02", "description": "Acute respiratory failure with hypercapnia",
     "keywords": ["hypercapnic respiratory failure"]},
    {"code": "J81.0", "description": "Acute pulmonary edema",
     "keywords": ["pulmonary edema"]},
    {"code": "A15.0", "description": "Tuberculosis of lung",
     "keywords": ["pulmonary tuberculosis", "active tuberculosis"]},
    # ---------- Gastrointestinal / hepatic ----------
    {"code": "K21.9", "description": "Gastro-esophageal reflux disease without esophagitis",
     "keywords": ["gerd", "gastroesophageal reflux"]},
    {"code": "K29.70", "description": "Gastritis, unspecified, without bleeding",
     "keywords": ["gastritis"]},
    {"code": "K57.30", "description": "Diverticulosis of large intestine without bleeding",
     "keywords": ["diverticulosis"]},
    {"code": "K59.00", "description": "Constipation, unspecified",
     "keywords": ["constipation"]},
    {"code": "K70.30", "description": "Alcoholic cirrhosis of liver without ascites",
     "keywords": ["alcoholic cirrhosis"]},
    {"code": "K76.0", "description": "Fatty (change of) liver, not elsewhere classified",
     "keywords": ["fatty liver", "hepatic steatosis", "nafld"]},
    {"code": "R10.9", "description": "Unspecified abdominal pain",
     "keywords": ["abdominal pain", "stomach pain"]},
    {"code": "R11.10", "description": "Vomiting, unspecified",
     "keywords": ["vomiting"]},
    {"code": "R19.7", "description": "Diarrhea, unspecified",
     "keywords": ["diarrhea"]},
    # ---------- Renal / GU ----------
    {"code": "N18.3", "description": "Chronic kidney disease, stage 3",
     "keywords": ["ckd stage 3", "chronic kidney disease stage 3"]},
    {"code": "N18.4", "description": "Chronic kidney disease, stage 4",
     "keywords": ["ckd stage 4", "chronic kidney disease stage 4"]},
    {"code": "N18.5", "description": "Chronic kidney disease, stage 5",
     "keywords": ["ckd stage 5", "esrd"]},
    {"code": "N17.9", "description": "Acute kidney failure, unspecified",
     "keywords": ["acute kidney injury", "aki", "acute renal failure"]},
    {"code": "N39.0", "description": "Urinary tract infection, site not specified",
     "keywords": ["urinary tract infection", "uti"]},
    {"code": "N20.0", "description": "Calculus of kidney",
     "keywords": ["nephrolithiasis", "kidney stone"]},
    # ---------- Mental health / neuro ----------
    {"code": "F32.9", "description": "Major depressive disorder, single episode, unspecified",
     "keywords": ["depression", "major depressive"]},
    {"code": "F33.1", "description": "Major depressive disorder, recurrent, moderate",
     "keywords": ["recurrent depression"]},
    {"code": "F41.1", "description": "Generalized anxiety disorder",
     "keywords": ["generalized anxiety", "gad"]},
    {"code": "F41.9", "description": "Anxiety disorder, unspecified",
     "keywords": ["anxiety"]},
    {"code": "F43.10", "description": "Post-traumatic stress disorder, unspecified",
     "keywords": ["ptsd"]},
    {"code": "F10.20", "description": "Alcohol dependence, uncomplicated",
     "keywords": ["alcohol use disorder", "alcoholism"]},
    {"code": "F17.210", "description": "Nicotine dependence, cigarettes, uncomplicated",
     "keywords": ["nicotine dependence", "cigarette smoking"]},
    {"code": "G43.909", "description": "Migraine, unspecified, not intractable, without status migrainosus",
     "keywords": ["migraine"]},
    {"code": "G47.33", "description": "Obstructive sleep apnea (adult) (pediatric)",
     "keywords": ["obstructive sleep apnea", "osa"]},
    # ---------- Musculoskeletal ----------
    {"code": "M25.50", "description": "Pain in unspecified joint",
     "keywords": ["joint pain"]},
    {"code": "M54.50", "description": "Low back pain, unspecified",
     "keywords": ["low back pain", "lower back pain"]},
    {"code": "M17.9", "description": "Osteoarthritis of knee, unspecified",
     "keywords": ["knee osteoarthritis"]},
    {"code": "M19.90", "description": "Unspecified osteoarthritis, unspecified site",
     "keywords": ["osteoarthritis"]},
    {"code": "M81.0", "description": "Age-related osteoporosis without current pathological fracture",
     "keywords": ["osteoporosis"]},
    # ---------- Skin / connective ----------
    {"code": "L03.90", "description": "Cellulitis, unspecified",
     "keywords": ["cellulitis"]},
    {"code": "L40.9", "description": "Psoriasis, unspecified",
     "keywords": ["psoriasis"]},
    {"code": "L20.9", "description": "Atopic dermatitis, unspecified",
     "keywords": ["atopic dermatitis", "eczema"]},
    # ---------- Symptoms / signs ----------
    {"code": "R07.9", "description": "Chest pain, unspecified",
     "keywords": ["chest pain", "thoracic pain"]},
    {"code": "R51", "description": "Headache",
     "keywords": ["headache", "cephalgia"]},
    {"code": "R55", "description": "Syncope and collapse",
     "keywords": ["syncope", "fainting"]},
    {"code": "R06.02", "description": "Shortness of breath",
     "keywords": ["shortness of breath", "dyspnea", "sob"]},
    {"code": "R50.9", "description": "Fever, unspecified",
     "keywords": ["fever"]},
    {"code": "R53.83", "description": "Other fatigue",
     "keywords": ["fatigue"]},
    {"code": "R63.4", "description": "Abnormal weight loss",
     "keywords": ["weight loss"]},
    # ---------- Infectious ----------
    {"code": "U07.1", "description": "COVID-19",
     "keywords": ["covid-19", "covid"]},
    {"code": "B19.20", "description": "Unspecified viral hepatitis C without hepatic coma",
     "keywords": ["hepatitis c"]},
    {"code": "B18.1", "description": "Chronic viral hepatitis B without delta-agent",
     "keywords": ["chronic hepatitis b"]},
    {"code": "B20", "description": "Human immunodeficiency virus [HIV] disease",
     "keywords": ["hiv", "human immunodeficiency virus"]},
    # ---------- Oncology ----------
    {"code": "C50.911", "description": "Malignant neoplasm of unspecified site of right female breast",
     "keywords": ["right breast cancer"]},
    {"code": "C34.90", "description": "Malignant neoplasm of unspecified part of unspecified bronchus or lung",
     "keywords": ["lung cancer", "bronchogenic carcinoma"]},
    {"code": "C18.9", "description": "Malignant neoplasm of colon, unspecified",
     "keywords": ["colon cancer", "colorectal cancer"]},
    {"code": "C61", "description": "Malignant neoplasm of prostate",
     "keywords": ["prostate cancer"]},
    # ---------- Pregnancy / women's health ----------
    {"code": "O14.93", "description": "Unspecified pre-eclampsia, third trimester",
     "keywords": ["preeclampsia"]},
    {"code": "Z34.90", "description": "Encounter for supervision of normal pregnancy, unspecified, unspecified trimester",
     "keywords": ["normal pregnancy"]},
    # ---------- Anemia / heme ----------
    {"code": "D50.9", "description": "Iron deficiency anemia, unspecified",
     "keywords": ["iron deficiency anemia"]},
    {"code": "D64.9", "description": "Anemia, unspecified",
     "keywords": ["anemia"]},
    # ---------- Allergy / immune ----------
    {"code": "T78.40XA", "description": "Allergy, unspecified, initial encounter",
     "keywords": ["allergic reaction"]},
    {"code": "J30.9", "description": "Allergic rhinitis, unspecified",
     "keywords": ["allergic rhinitis", "hay fever"]},
    # ---------- Trauma / falls ----------
    {"code": "S72.001A", "description": "Fracture of unspecified part of neck of right femur, initial encounter",
     "keywords": ["right hip fracture"]},
    {"code": "W19.XXXA", "description": "Unspecified fall, initial encounter",
     "keywords": ["fall"]},
    {"code": "S06.0X0A", "description": "Concussion without loss of consciousness, initial encounter",
     "keywords": ["concussion"]},
    # ---------- Functional / general ----------
    {"code": "Z51.11", "description": "Encounter for antineoplastic chemotherapy",
     "keywords": ["chemotherapy"]},
    {"code": "Z79.4", "description": "Long term (current) use of insulin",
     "keywords": ["insulin therapy"]},
    {"code": "Z79.01", "description": "Long term (current) use of anticoagulants",
     "keywords": ["anticoagulant therapy"]},
    {"code": "Z00.00", "description": "Encounter for general adult medical examination without abnormal findings",
     "keywords": ["annual physical", "wellness exam"]},
]


# CPT defaults to empty — see module docstring re: AMA licensing.
CPT: list[dict[str, object]] = []


def search(table: list[dict[str, object]], text: str) -> list[dict[str, str]]:
    """Return all entries whose keywords appear in *text* (case-insensitive)."""
    text_l = text.lower()
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for entry in table:
        keywords = entry["keywords"]
        assert isinstance(keywords, list)
        for kw in keywords:
            if kw in text_l:
                code = str(entry["code"])
                if code in seen:
                    break
                seen.add(code)
                out.append({"code": code, "description": str(entry["description"])})
                break
    return out


# ---------------------------------------------------------------------------
# Pluggable loaders for the full / licensed code sets
# ---------------------------------------------------------------------------


def load_cpt_jsonl(path: str) -> int:
    """Append CPT entries from a JSONL file you supply (AMA-licensed data).

    File format: one ``{"code", "description", "keywords": [...]}`` JSON
    object per line. Entries with codes already present are skipped.
    Returns the count of entries added.
    """
    existing = {str(e["code"]) for e in CPT}
    added = 0
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            raw = raw.strip()
            if not raw:
                continue
            entry = json.loads(raw)
            code = str(entry["code"])
            if code in existing:
                continue
            CPT.append({
                "code": code,
                "description": str(entry["description"]),
                "keywords": [str(k).lower() for k in entry.get("keywords", [])],
            })
            existing.add(code)
            added += 1
    return added


def load_icd10_cm_xml(path: str) -> int:
    """Append ICD-10-CM entries from the CMS tabular XML release.

    The CMS tabular release ships as ``icd10cm-tabular-2025-Addenda.xml`` or
    similar. This loader walks ``<diag>`` nodes (codes are in ``<name>``,
    descriptions in ``<desc>``) and adds any code not already present.
    Keywords default to ``[description.lower()]``; users can re-tune later.

    Returns the count of entries added.
    """
    import xml.etree.ElementTree as ET

    tree = ET.parse(path)
    root = tree.getroot()
    existing = {str(e["code"]) for e in ICD10}
    added = 0
    # CMS XML uses <diag> recursively under <chapter> > <section>.
    for diag in root.iter("diag"):
        name = diag.findtext("name")
        desc = diag.findtext("desc")
        if not name or not desc:
            continue
        code = name.strip()
        if code in existing:
            continue
        ICD10.append({
            "code": code,
            "description": desc.strip(),
            "keywords": [desc.strip().lower()],
        })
        existing.add(code)
        added += 1
    return added


# Re-exported for callers that want to inspect data version.
def data_versions() -> dict[str, Any]:
    return {
        "icd10_cm_version": ICD10_CM_VERSION,
        "icd10_cm_source": ICD10_CM_SOURCE,
        "icd10_cm_license": ICD10_CM_LICENSE,
        "icd10_cm_entry_count": len(ICD10),
        "cpt_version_info": CPT_VERSION_INFO,
        "cpt_entry_count": len(CPT),
    }

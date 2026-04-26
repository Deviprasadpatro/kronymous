"""Sample ICD-10 / CPT lookup tables.

This is a small, illustrative subset suitable for demos and tests. Production
deployments should plug in a maintained code set (e.g. AHIMA, AMA CPT®).
"""

from __future__ import annotations

# Each entry maps a list of trigger keywords/phrases (case-insensitive) to a code.
ICD10: list[dict[str, object]] = [
    {"code": "I10", "description": "Essential (primary) hypertension",
     "keywords": ["hypertension", "high blood pressure", "htn", "elevated bp"]},
    {"code": "E11.9", "description": "Type 2 diabetes mellitus without complications",
     "keywords": ["type 2 diabetes", "t2dm", "dm2", "diabetes mellitus type 2"]},
    {"code": "E11.65", "description": "Type 2 diabetes mellitus with hyperglycemia",
     "keywords": ["uncontrolled diabetes", "hyperglycemia"]},
    {"code": "I50.9", "description": "Heart failure, unspecified",
     "keywords": ["heart failure", "chf", "congestive heart failure"]},
    {"code": "J44.9", "description": "Chronic obstructive pulmonary disease, unspecified",
     "keywords": ["copd", "chronic obstructive pulmonary disease"]},
    {"code": "N18.3", "description": "Chronic kidney disease, stage 3",
     "keywords": ["ckd stage 3", "chronic kidney disease stage 3"]},
    {"code": "J18.9", "description": "Pneumonia, unspecified organism",
     "keywords": ["pneumonia", "lower respiratory infection"]},
    {"code": "R07.9", "description": "Chest pain, unspecified",
     "keywords": ["chest pain", "thoracic pain"]},
    {"code": "R51", "description": "Headache",
     "keywords": ["headache", "cephalgia"]},
    {"code": "R10.9", "description": "Unspecified abdominal pain",
     "keywords": ["abdominal pain", "stomach pain"]},
    {"code": "J45.909", "description": "Unspecified asthma, uncomplicated",
     "keywords": ["asthma"]},
    {"code": "F32.9", "description": "Major depressive disorder, single episode, unspecified",
     "keywords": ["depression", "major depressive"]},
]

CPT: list[dict[str, object]] = [
    {"code": "99213", "description": "Office/outpatient visit, established patient (low-to-moderate complexity)",
     "keywords": ["follow-up visit", "established patient", "office visit"]},
    {"code": "99214", "description": "Office/outpatient visit, established patient (moderate complexity)",
     "keywords": ["moderate complexity", "multiple chronic conditions"]},
    {"code": "93000", "description": "Electrocardiogram, complete",
     "keywords": ["ecg", "ekg", "electrocardiogram"]},
    {"code": "71046", "description": "Chest x-ray, 2 views",
     "keywords": ["chest x-ray", "cxr", "chest radiograph"]},
    {"code": "80053", "description": "Comprehensive metabolic panel",
     "keywords": ["cmp", "comprehensive metabolic panel"]},
    {"code": "85025", "description": "Complete blood count with differential",
     "keywords": ["cbc", "complete blood count"]},
    {"code": "83036", "description": "Hemoglobin A1c",
     "keywords": ["a1c", "hba1c", "hemoglobin a1c"]},
]


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

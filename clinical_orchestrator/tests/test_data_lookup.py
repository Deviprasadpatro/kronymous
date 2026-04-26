"""Tests for ICD-10-CM expanded lookup + pluggable CPT loader + protocol provenance."""

from __future__ import annotations

import json

from clinical_orchestrator.data.icd10_cpt import (
    CPT,
    ICD10,
    data_versions,
    load_cpt_jsonl,
    search,
)
from clinical_orchestrator.data.protocols import (
    PROTOCOL_CITATIONS,
    PROTOCOL_VERSION,
    protocol_versions,
)


def test_icd10_table_has_expanded_real_codes():
    """The bundled ICD-10-CM table should include common chronic / ED codes."""
    codes = {str(e["code"]) for e in ICD10}
    # Sample of widely-used codes that *must* be present after expansion.
    must_have = {
        "I10", "I50.9", "E11.9", "E11.65", "J18.9", "J44.9",
        "N18.3", "N17.9", "F32.9", "F41.1", "U07.1",
    }
    missing = must_have - codes
    assert not missing, f"expected ICD-10 codes missing: {missing}"
    assert len(codes) >= 80, f"expected >=80 ICD-10 entries, got {len(codes)}"


def test_search_finds_multiple_matches_in_one_text():
    text = "Patient with hypertension, type 2 diabetes, and shortness of breath."
    out = search(ICD10, text)
    found = {row["code"] for row in out}
    assert "I10" in found
    assert "E11.9" in found
    assert "R06.02" in found


def test_search_is_case_insensitive():
    out = search(ICD10, "PATIENT HAS HEART FAILURE")
    assert any(r["code"] == "I50.9" for r in out)


def test_cpt_table_empty_by_default():
    """CPT must be empty by default (AMA licensing)."""
    assert CPT == [], (
        "CPT table must be empty by default — AMA-licensed data cannot be bundled. "
        "Use load_cpt_jsonl() to plug in your licensed code set."
    )


def test_load_cpt_jsonl_populates_table(tmp_path):
    p = tmp_path / "cpt.jsonl"
    rows = [
        {"code": "99213", "description": "Office visit, est., low/mod complexity",
         "keywords": ["follow-up visit"]},
        {"code": "93000", "description": "ECG, complete",
         "keywords": ["ecg", "ekg"]},
    ]
    p.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    try:
        added = load_cpt_jsonl(str(p))
        assert added == 2
        assert any(e["code"] == "99213" for e in CPT)
        out = search(CPT, "Performed ECG today.")
        assert any(r["code"] == "93000" for r in out)
    finally:
        # restore module-level state for other tests
        CPT.clear()


def test_data_versions_reports_provenance():
    info = data_versions()
    assert info["icd10_cm_version"] == "FY2025"
    assert "Public Domain" in info["icd10_cm_license"]
    assert info["icd10_cm_entry_count"] >= 80
    assert "AMA-licensed" in info["cpt_version_info"]


def test_protocol_versions_has_citations():
    info = protocol_versions()
    assert info["protocol_version"] == PROTOCOL_VERSION
    # Must cite at least every primary chronic-care condition we monitor.
    for cond in ("hypertension", "diabetes", "heart_failure", "copd", "ckd"):
        assert cond in PROTOCOL_CITATIONS, f"missing citation for {cond}"
        assert PROTOCOL_CITATIONS[cond], f"empty citation list for {cond}"

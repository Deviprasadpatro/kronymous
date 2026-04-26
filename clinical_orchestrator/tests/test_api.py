from fastapi.testclient import TestClient

from clinical_orchestrator.api.server import create_app
from clinical_orchestrator.core.orchestrator import ClinicalOrchestrator


def _client():
    orch = ClinicalOrchestrator()
    return TestClient(create_app(orch))


def test_health_endpoint():
    client = _client()
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert set(body["agents"]) == {"documentation", "chronic_care", "diagnostic"}


def test_full_flow():
    client = _client()
    pid = "P-API"
    r = client.post("/patients", json={
        "patient_id": pid,
        "conditions": ["hypertension"],
        "allergies": ["penicillin"],
    })
    assert r.status_code == 200

    r = client.post("/documentation", json={
        "patient_id": pid,
        "transcript": "S: Headache.\nO: BP 150/95.\nA: HTN.\nP: Continue lisinopril.",
    })
    assert r.status_code == 200
    assert r.json()["action_id"]

    r = client.post("/vitals", json={
        "patient_id": pid,
        "vitals": [{"name": "systolic_bp", "value": 150, "unit": "mmHg"}],
    })
    assert r.status_code == 200

    r = client.get("/reviews", params={"patient_id": pid})
    assert r.status_code == 200
    pending = r.json()
    assert pending
    aid = pending[0]["action_id"]
    r = client.post(f"/reviews/{aid}/confirm", json={"reviewer": "dr.api"})
    assert r.status_code == 200
    assert r.json()["status"] == "confirmed"

    r = client.get(f"/patients/{pid}")
    assert r.status_code == 200
    body = r.json()
    assert body["codes"] or body["care_plan"]


def test_modify_review_requires_final_action():
    client = _client()
    client.post("/patients", json={"patient_id": "P-MOD"})
    client.post("/documentation", json={"patient_id": "P-MOD", "transcript": "S: pain."})
    pending = client.get("/reviews", params={"patient_id": "P-MOD"}).json()
    aid = pending[0]["action_id"]
    r = client.post(f"/reviews/{aid}/modify", json={"reviewer": "dr.api"})
    assert r.status_code == 400

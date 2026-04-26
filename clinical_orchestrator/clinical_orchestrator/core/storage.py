"""Pluggable persistent storage for the Clinical Orchestrator.

The default deployment is fully in-memory (:class:`MemoryStorage`).
Production / multi-restart deployments can pick :class:`SqliteStorage`,
which persists patients, HITL actions, audit entries, and replayed events
to a single sqlite file.

Selected via env var ``CLINICAL_STORAGE_URL``:

    memory://                     # default
    sqlite:///path/to/db.sqlite   # file-backed

The :class:`PatientRegistry`, :class:`SafetyGate`, and :class:`AuditLog`
classes accept an optional storage instance and *mirror* every mutation
into it so reads still hit the in-memory copy (fast) and crashes don't
lose state.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from typing import Any, Protocol

from .audit import AuditEntry
from .context import LabResult, PatientContext, VitalReading
from .safety import PendingAction


@dataclass
class StoredEvent:
    topic: str
    payload: dict[str, Any]
    source: str
    patient_id: str | None
    severity: str
    event_id: str
    timestamp: float


class Storage(Protocol):
    """Abstract storage interface; both Memory and Sqlite implement it."""

    def save_patient(self, patient: PatientContext) -> None: ...
    def load_patient(self, patient_id: str) -> PatientContext | None: ...
    def list_patients(self) -> list[PatientContext]: ...

    def save_action(self, action: PendingAction) -> None: ...
    def load_actions(self) -> list[PendingAction]: ...

    def append_audit(self, entry: AuditEntry) -> None: ...
    def list_audit(self) -> list[AuditEntry]: ...

    def append_event(self, event: StoredEvent) -> None: ...
    def list_events(self, topic_prefix: str | None = None) -> list[StoredEvent]: ...

    def close(self) -> None: ...


# ---------------------------------------------------------------------------
# In-memory implementation (the historical default)
# ---------------------------------------------------------------------------


class MemoryStorage:
    """No-op persistence — useful for tests and ephemeral demos."""

    def __init__(self) -> None:
        self._patients: dict[str, PatientContext] = {}
        self._actions: dict[str, PendingAction] = {}
        self._audit: list[AuditEntry] = []
        self._events: list[StoredEvent] = []
        self._lock = threading.RLock()

    def save_patient(self, patient: PatientContext) -> None:
        with self._lock:
            self._patients[patient.patient_id] = patient

    def load_patient(self, patient_id: str) -> PatientContext | None:
        with self._lock:
            return self._patients.get(patient_id)

    def list_patients(self) -> list[PatientContext]:
        with self._lock:
            return list(self._patients.values())

    def save_action(self, action: PendingAction) -> None:
        with self._lock:
            self._actions[action.action_id] = action

    def load_actions(self) -> list[PendingAction]:
        with self._lock:
            return list(self._actions.values())

    def append_audit(self, entry: AuditEntry) -> None:
        with self._lock:
            self._audit.append(entry)

    def list_audit(self) -> list[AuditEntry]:
        with self._lock:
            return list(self._audit)

    def append_event(self, event: StoredEvent) -> None:
        with self._lock:
            self._events.append(event)

    def list_events(self, topic_prefix: str | None = None) -> list[StoredEvent]:
        with self._lock:
            if topic_prefix is None:
                return list(self._events)
            return [e for e in self._events if e.topic.startswith(topic_prefix)]

    def close(self) -> None:  # pragma: no cover - nothing to release
        pass


# ---------------------------------------------------------------------------
# SQLite implementation
# ---------------------------------------------------------------------------


_SCHEMA = """
CREATE TABLE IF NOT EXISTS patients (
    patient_id TEXT PRIMARY KEY,
    blob TEXT NOT NULL,
    updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS actions (
    action_id TEXT PRIMARY KEY,
    patient_id TEXT,
    actor TEXT NOT NULL,
    status TEXT NOT NULL,
    blob TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_actions_patient ON actions(patient_id);
CREATE INDEX IF NOT EXISTS idx_actions_status ON actions(status);

CREATE TABLE IF NOT EXISTS audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    patient_id TEXT,
    detail TEXT NOT NULL,
    timestamp REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_actor ON audit(actor);

CREATE TABLE IF NOT EXISTS events (
    event_id TEXT PRIMARY KEY,
    topic TEXT NOT NULL,
    source TEXT NOT NULL,
    patient_id TEXT,
    severity TEXT NOT NULL,
    payload TEXT NOT NULL,
    timestamp REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_topic ON events(topic);
"""


class SqliteStorage:
    """File-backed persistence using stdlib sqlite3.

    Thread-safe via a process-wide lock + ``check_same_thread=False``. The
    schema is created on startup and is forward-compatible with older
    databases (CREATE TABLE IF NOT EXISTS).
    """

    def __init__(self, path: str) -> None:
        self.path = path
        # Ensure parent dir exists.
        parent = os.path.dirname(os.path.abspath(path))
        if parent:
            os.makedirs(parent, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._lock = threading.RLock()
        with self._lock:
            self._conn.executescript(_SCHEMA)

    # -- patients --------------------------------------------------------
    def save_patient(self, patient: PatientContext) -> None:
        blob = json.dumps(_patient_to_dict(patient))
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO patients(patient_id, blob, updated_at) VALUES (?,?,?)",
                (patient.patient_id, blob, time.time()),
            )

    def load_patient(self, patient_id: str) -> PatientContext | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT blob FROM patients WHERE patient_id=?",
                (patient_id,),
            ).fetchone()
        if not row:
            return None
        return _patient_from_dict(json.loads(row[0]))

    def list_patients(self) -> list[PatientContext]:
        with self._lock:
            rows = self._conn.execute("SELECT blob FROM patients").fetchall()
        return [_patient_from_dict(json.loads(r[0])) for r in rows]

    # -- actions ---------------------------------------------------------
    def save_action(self, action: PendingAction) -> None:
        blob = json.dumps(_action_to_dict(action))
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO actions"
                "(action_id, patient_id, actor, status, blob, created_at, updated_at)"
                " VALUES (?,?,?,?,?,?,?)",
                (
                    action.action_id,
                    action.patient_id,
                    action.actor,
                    action.status,
                    blob,
                    action.created_at,
                    time.time(),
                ),
            )

    def load_actions(self) -> list[PendingAction]:
        with self._lock:
            rows = self._conn.execute("SELECT blob FROM actions").fetchall()
        return [_action_from_dict(json.loads(r[0])) for r in rows]

    # -- audit -----------------------------------------------------------
    def append_audit(self, entry: AuditEntry) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO audit(actor, action, patient_id, detail, timestamp) VALUES (?,?,?,?,?)",
                (entry.actor, entry.action, entry.patient_id, json.dumps(entry.detail), entry.timestamp),
            )

    def list_audit(self) -> list[AuditEntry]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT actor, action, patient_id, detail, timestamp FROM audit ORDER BY id ASC"
            ).fetchall()
        out: list[AuditEntry] = []
        for r in rows:
            out.append(
                AuditEntry(
                    actor=r[0],
                    action=r[1],
                    patient_id=r[2],
                    detail=json.loads(r[3]),
                    timestamp=r[4],
                )
            )
        return out

    # -- events ----------------------------------------------------------
    def append_event(self, event: StoredEvent) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO events"
                "(event_id, topic, source, patient_id, severity, payload, timestamp)"
                " VALUES (?,?,?,?,?,?,?)",
                (
                    event.event_id,
                    event.topic,
                    event.source,
                    event.patient_id,
                    event.severity,
                    json.dumps(event.payload),
                    event.timestamp,
                ),
            )

    def list_events(self, topic_prefix: str | None = None) -> list[StoredEvent]:
        sql = "SELECT event_id, topic, source, patient_id, severity, payload, timestamp FROM events"
        params: tuple[Any, ...] = ()
        if topic_prefix:
            sql += " WHERE topic LIKE ?"
            params = (topic_prefix + "%",)
        sql += " ORDER BY timestamp ASC"
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [
            StoredEvent(
                event_id=r[0], topic=r[1], source=r[2], patient_id=r[3],
                severity=r[4], payload=json.loads(r[5]), timestamp=r[6],
            )
            for r in rows
        ]

    def close(self) -> None:
        with self._lock:
            self._conn.close()


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def make_storage(url: str | None = None) -> Storage:
    """Construct a Storage from a URL or env (``CLINICAL_STORAGE_URL``).

    ``memory://`` (default), ``sqlite:///path/to/db.sqlite``.
    """
    url = url or os.environ.get("CLINICAL_STORAGE_URL") or "memory://"
    if url.startswith("memory://"):
        return MemoryStorage()
    if url.startswith("sqlite:///"):
        path = url[len("sqlite:///"):]
        return SqliteStorage(path)
    if url.startswith("sqlite://"):
        # sqlite://relative.db form
        path = url[len("sqlite://"):]
        return SqliteStorage(path)
    raise ValueError(f"Unsupported storage URL: {url!r}")


# ---------------------------------------------------------------------------
# (de)serialization helpers
# ---------------------------------------------------------------------------


def _patient_to_dict(p: PatientContext) -> dict[str, Any]:
    return {
        "patient_id": p.patient_id,
        "name": p.name,
        "dob": p.dob,
        "sex": p.sex,
        "mrn": p.mrn,
        "allergies": list(p.allergies),
        "conditions": list(p.conditions),
        "medications": list(p.medications),
        "vitals": [asdict(v) for v in p.vitals],
        "labs": [asdict(lab) for lab in p.labs],
        # Findings hold a spatial_ref dict that may include numpy-ish types;
        # callers always pass plain dicts in this codebase, so json.dumps is safe.
        "findings": [
            {
                "source": f.source,
                "description": f.description,
                "confidence": f.confidence,
                "spatial_ref": f.spatial_ref,
                "citations": list(f.citations),
                "timestamp": f.timestamp,
            }
            for f in p.findings
        ],
        "soap_note": dict(p.soap_note),
        "codes": [dict(c) for c in p.codes],
        "care_plan": list(p.care_plan),
        "kpis": dict(p.kpis),
        "notes": list(p.notes),
    }


def _patient_from_dict(d: dict[str, Any]) -> PatientContext:
    from .context import Finding  # local import to avoid cycles

    p = PatientContext(
        patient_id=d["patient_id"],
        name=d.get("name", ""),
        dob=d.get("dob", ""),
        sex=d.get("sex", ""),
        mrn=d.get("mrn", ""),
        allergies=list(d.get("allergies", [])),
        conditions=list(d.get("conditions", [])),
        medications=list(d.get("medications", [])),
        soap_note=dict(d.get("soap_note", {})),
        codes=[dict(c) for c in d.get("codes", [])],
        care_plan=list(d.get("care_plan", [])),
        kpis=dict(d.get("kpis", {})),
        notes=list(d.get("notes", [])),
    )
    for v in d.get("vitals", []):
        p.vitals.append(VitalReading(**v))
    for lab in d.get("labs", []):
        p.labs.append(LabResult(**lab))
    for f in d.get("findings", []):
        p.findings.append(
            Finding(
                source=f["source"],
                description=f["description"],
                confidence=f.get("confidence", 0.0),
                spatial_ref=f.get("spatial_ref"),
                citations=list(f.get("citations", [])),
                timestamp=f.get("timestamp", time.time()),
            )
        )
    return p


def _action_to_dict(a: PendingAction) -> dict[str, Any]:
    return {
        "action_id": a.action_id,
        "actor": a.actor,
        "description": a.description,
        "rationale": a.rationale,
        "evidence": list(a.evidence),
        "suggested_action": dict(a.suggested_action),
        "severity": a.severity,
        "status": a.status,
        "patient_id": a.patient_id,
        "created_at": a.created_at,
        "reviewed_at": a.reviewed_at,
        "reviewer": a.reviewer,
        "final_action": dict(a.final_action) if a.final_action is not None else None,
    }


def _action_from_dict(d: dict[str, Any]) -> PendingAction:
    return PendingAction(
        action_id=d["action_id"],
        actor=d["actor"],
        description=d["description"],
        rationale=d["rationale"],
        evidence=list(d.get("evidence", [])),
        suggested_action=dict(d.get("suggested_action", {})),
        severity=d.get("severity", "notice"),
        status=d.get("status", "pending"),
        patient_id=d.get("patient_id"),
        created_at=d.get("created_at", time.time()),
        reviewed_at=d.get("reviewed_at"),
        reviewer=d.get("reviewer"),
        final_action=d.get("final_action"),
    )


# Avoid unused-import lint noise
_ = (Iterable,)

"""Append-only structured audit log."""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover
    from .storage import Storage


@dataclass
class AuditEntry:
    actor: str
    action: str
    detail: dict[str, Any] = field(default_factory=dict)
    patient_id: str | None = None
    timestamp: float = field(default_factory=time.time)


class AuditLog:
    """Thread-safe in-memory audit log with optional JSONL + Storage mirror."""

    def __init__(self, path: str | None = None, storage: Storage | None = None) -> None:
        self.path = path or os.environ.get("CLINICAL_ORCHESTRATOR_AUDIT_PATH")
        self.storage = storage
        self._entries: list[AuditEntry] = []
        self._lock = threading.RLock()
        # Replay from durable storage if present so a fresh process sees history.
        if storage is not None:
            try:
                self._entries.extend(storage.list_audit())
            except Exception:  # pragma: no cover - defensive
                pass

    def record(
        self,
        actor: str,
        action: str,
        detail: dict[str, Any] | None = None,
        patient_id: str | None = None,
    ) -> AuditEntry:
        entry = AuditEntry(actor=actor, action=action, detail=detail or {}, patient_id=patient_id)
        with self._lock:
            self._entries.append(entry)
            if self.path:
                try:
                    with open(self.path, "a", encoding="utf-8") as fh:
                        fh.write(json.dumps(asdict(entry)) + "\n")
                except OSError:  # pragma: no cover - defensive
                    pass
            if self.storage is not None:
                try:
                    self.storage.append_audit(entry)
                except Exception:  # pragma: no cover - defensive
                    pass
        return entry

    def entries(self, actor: str | None = None) -> list[AuditEntry]:
        with self._lock:
            if actor is None:
                return list(self._entries)
            return [e for e in self._entries if e.actor == actor]

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

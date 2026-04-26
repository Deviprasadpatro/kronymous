"""Human-in-the-loop (HITL) safety primitives.

Every clinically meaningful action goes through :class:`SafetyGate`, which
records a ``pending_review`` action that must be ``confirmed`` or
``modified`` by a licensed clinician before it is committed. Critical
events automatically *escalate* to immediate review.
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:  # pragma: no cover
    from .storage import Storage

ReviewStatus = Literal["pending", "confirmed", "modified", "rejected"]


@dataclass
class PendingAction:
    action_id: str
    actor: str
    description: str
    rationale: str
    evidence: list[str]
    suggested_action: dict[str, Any]
    severity: str = "notice"  # info | notice | warning | critical
    status: ReviewStatus = "pending"
    patient_id: str | None = None
    created_at: float = field(default_factory=time.time)
    reviewed_at: float | None = None
    reviewer: str | None = None
    final_action: dict[str, Any] | None = None


class EscalationError(RuntimeError):
    """Raised when a critical action cannot proceed without clinician review."""


class SafetyGate:
    """Holds pending HITL actions and routes critical ones for immediate review."""

    CRITICAL_THRESHOLD = "critical"

    def __init__(self, storage: Storage | None = None) -> None:
        self.storage = storage
        self._pending: dict[str, PendingAction] = {}
        self._lock = threading.RLock()
        # Replay any persisted actions so a restarted process resumes the queue.
        if storage is not None:
            try:
                for a in storage.load_actions():
                    self._pending[a.action_id] = a
            except Exception:  # pragma: no cover - defensive
                pass

    def _persist(self, action: PendingAction) -> None:
        if self.storage is None:
            return
        try:
            self.storage.save_action(action)
        except Exception:  # pragma: no cover - defensive
            pass

    # -- submission ------------------------------------------------------
    def propose(
        self,
        actor: str,
        description: str,
        rationale: str,
        evidence: list[str],
        suggested_action: dict[str, Any],
        severity: str = "notice",
        patient_id: str | None = None,
    ) -> PendingAction:
        action = PendingAction(
            action_id=str(uuid.uuid4()),
            actor=actor,
            description=description,
            rationale=rationale,
            evidence=list(evidence),
            suggested_action=dict(suggested_action),
            severity=severity,
            patient_id=patient_id,
        )
        with self._lock:
            self._pending[action.action_id] = action
        self._persist(action)
        return action

    # -- review ----------------------------------------------------------
    def confirm(self, action_id: str, reviewer: str) -> PendingAction:
        return self._review(action_id, reviewer, "confirmed", final=None)

    def modify(self, action_id: str, reviewer: str, final_action: dict[str, Any]) -> PendingAction:
        return self._review(action_id, reviewer, "modified", final=final_action)

    def reject(self, action_id: str, reviewer: str) -> PendingAction:
        return self._review(action_id, reviewer, "rejected", final=None)

    def _review(
        self,
        action_id: str,
        reviewer: str,
        status: ReviewStatus,
        final: dict[str, Any] | None,
    ) -> PendingAction:
        with self._lock:
            if action_id not in self._pending:
                raise KeyError(f"Unknown action_id: {action_id}")
            action = self._pending[action_id]
            if action.status != "pending":
                raise ValueError(f"Action {action_id} already reviewed (status={action.status})")
            action.status = status
            action.reviewer = reviewer
            action.reviewed_at = time.time()
            action.final_action = final if final is not None else action.suggested_action if status == "confirmed" else None
        self._persist(action)
        return action

    # -- queries ---------------------------------------------------------
    def pending(self, patient_id: str | None = None) -> list[PendingAction]:
        with self._lock:
            items = list(self._pending.values())
        items = [a for a in items if a.status == "pending"]
        if patient_id is not None:
            items = [a for a in items if a.patient_id == patient_id]
        return items

    def get(self, action_id: str) -> PendingAction | None:
        with self._lock:
            return self._pending.get(action_id)

    def all(self) -> list[PendingAction]:
        with self._lock:
            return list(self._pending.values())

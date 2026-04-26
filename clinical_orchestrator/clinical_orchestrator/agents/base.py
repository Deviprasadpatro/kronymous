"""Base classes for Clinical Orchestrator agents."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ..core.audit import AuditLog
from ..core.context import PatientContext
from ..core.event_bus import ClinicalEvent, EventBus
from ..core.llm import LLMProvider
from ..core.safety import SafetyGate


class Agent(ABC):
    """Common surface for every agent in the system."""

    name: str = "agent"

    def __init__(
        self,
        bus: EventBus,
        safety: SafetyGate,
        audit: AuditLog,
        llm: LLMProvider | None = None,
    ) -> None:
        self.bus = bus
        self.safety = safety
        self.audit = audit
        self.llm = llm or LLMProvider()

    def emit(self, topic: str, payload: dict[str, Any], patient_id: str | None = None,
             severity: str = "info") -> None:
        self.bus.publish(
            ClinicalEvent(
                topic=topic,
                payload=payload,
                source=self.name,
                patient_id=patient_id,
                severity=severity,
            )
        )

    def health_check(self, patient: PatientContext | None = None) -> bool:
        """Return True if a known-good fixture can be processed.

        Default implementation just returns ``True``; agents override with
        a real probe so :class:`SelfDebugger` can verify recovery.
        """
        return True

    @abstractmethod
    def run(self, *args: Any, **kwargs: Any) -> Any: ...

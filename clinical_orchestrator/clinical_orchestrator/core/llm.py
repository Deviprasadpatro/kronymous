"""LLM provider abstraction.

The orchestrator works fully offline using deterministic rule-based agents.
This module exists so any agent can *optionally* call into a real LLM
(OpenAI-compatible) when ``OPENAI_API_KEY`` is set. On any error or when no
key is present, the provider returns ``None`` so callers can fall back to
their rule-based path.
"""

from __future__ import annotations

import os
from typing import Any


class LLMProvider:
    """Minimal OpenAI-compatible chat wrapper.

    Returns ``None`` instead of raising whenever the LLM is unavailable so
    callers can transparently fall back to deterministic logic.
    """

    def __init__(self, model: str | None = None) -> None:
        self.model = model or os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        self._client: Any | None = None
        self._tried_init = False

    @property
    def available(self) -> bool:
        return bool(os.environ.get("OPENAI_API_KEY"))

    def _ensure_client(self) -> Any | None:
        if self._tried_init:
            return self._client
        self._tried_init = True
        if not self.available:
            return None
        try:
            from openai import OpenAI  # type: ignore
        except Exception:
            return None
        try:
            self._client = OpenAI()
        except Exception:
            self._client = None
        return self._client

    def complete(self, system: str, user: str, **kwargs: Any) -> str | None:
        client = self._ensure_client()
        if client is None:
            return None
        try:
            resp = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                **kwargs,
            )
            return resp.choices[0].message.content
        except Exception:
            return None

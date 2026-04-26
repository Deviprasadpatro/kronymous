"""LLM provider abstraction.

The orchestrator works fully offline using deterministic rule-based agents.
This module exists so any agent can *optionally* call into a real LLM when
credentials are available. On any error or when no provider can be
constructed, the public methods return ``None`` so callers can fall back to
their rule-based path.

Supported backends (auto-selected by ``CLINICAL_LLM_PROVIDER``):

* ``openai``   — env: ``OPENAI_API_KEY`` (+ optional ``OPENAI_MODEL``)
* ``anthropic``— env: ``ANTHROPIC_API_KEY`` (+ optional ``ANTHROPIC_MODEL``)
* ``gemini``   — env: ``GEMINI_API_KEY`` (+ optional ``GEMINI_MODEL``)
* ``auto``     — first of the above with both creds AND library installed (default)
* ``none``     — disable all (forces rule-based fallback)

Install backends via the relevant extras:

    pip install -e ".[openai]"
    pip install -e ".[anthropic]"
    pip install -e ".[gemini]"
    pip install -e ".[llm]"   # installs all three
"""

from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from typing import Any


class _Backend(ABC):
    """One concrete LLM provider integration."""

    name: str = "abstract"

    @property
    @abstractmethod
    def available(self) -> bool: ...

    @abstractmethod
    def complete(self, system: str, user: str, **kwargs: Any) -> str | None: ...

    def complete_json(
        self,
        system: str,
        user: str,
        schema: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any] | None:
        """Default JSON mode: ask the model to return JSON, parse defensively."""
        sys_json = system + "\nReturn STRICT JSON only — no markdown, no prose."
        out = self.complete(system=sys_json, user=user, **kwargs)
        if not out:
            return None
        try:
            data = json.loads(out)
            if isinstance(data, dict):
                return data
            return None
        except (json.JSONDecodeError, TypeError):
            return None


class _OpenAIBackend(_Backend):
    name = "openai"

    def __init__(self, model: str | None = None) -> None:
        self.model = model or os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        self._client: Any | None = None
        self._tried_init = False

    @property
    def available(self) -> bool:
        return bool(os.environ.get("OPENAI_API_KEY"))

    def _client_or_none(self) -> Any | None:
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
        client = self._client_or_none()
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

    def complete_json(
        self,
        system: str,
        user: str,
        schema: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any] | None:
        client = self._client_or_none()
        if client is None:
            return None
        # Use OpenAI's JSON mode for stricter parsing.
        params = dict(kwargs)
        params.setdefault("response_format", {"type": "json_object"})
        try:
            resp = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                **params,
            )
            text = resp.choices[0].message.content
            if not text:
                return None
            data = json.loads(text)
            if isinstance(data, dict):
                return data
            return None
        except Exception:
            # fall back to default text-then-parse behavior
            return super().complete_json(system, user, schema=schema, **kwargs)


class _AnthropicBackend(_Backend):
    name = "anthropic"

    def __init__(self, model: str | None = None) -> None:
        self.model = model or os.environ.get("ANTHROPIC_MODEL", "claude-3-5-sonnet-latest")
        self._client: Any | None = None
        self._tried_init = False

    @property
    def available(self) -> bool:
        return bool(os.environ.get("ANTHROPIC_API_KEY"))

    def _client_or_none(self) -> Any | None:
        if self._tried_init:
            return self._client
        self._tried_init = True
        if not self.available:
            return None
        try:
            import anthropic  # type: ignore
        except Exception:
            return None
        try:
            self._client = anthropic.Anthropic()
        except Exception:
            self._client = None
        return self._client

    def complete(self, system: str, user: str, **kwargs: Any) -> str | None:
        client = self._client_or_none()
        if client is None:
            return None
        try:
            resp = client.messages.create(
                model=self.model,
                max_tokens=kwargs.pop("max_tokens", 1024),
                system=system,
                messages=[{"role": "user", "content": user}],
                **kwargs,
            )
            # resp.content is a list of content blocks
            for block in resp.content:
                text = getattr(block, "text", None)
                if text:
                    return text
            return None
        except Exception:
            return None


class _GeminiBackend(_Backend):
    name = "gemini"

    def __init__(self, model: str | None = None) -> None:
        self.model = model or os.environ.get("GEMINI_MODEL", "gemini-1.5-flash")
        self._client: Any | None = None
        self._tried_init = False

    @property
    def available(self) -> bool:
        return bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))

    def _client_or_none(self) -> Any | None:
        if self._tried_init:
            return self._client
        self._tried_init = True
        if not self.available:
            return None
        try:
            import google.generativeai as genai  # type: ignore
        except Exception:
            return None
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        try:
            genai.configure(api_key=api_key)
            self._client = genai.GenerativeModel(self.model)
        except Exception:
            self._client = None
        return self._client

    def complete(self, system: str, user: str, **kwargs: Any) -> str | None:
        client = self._client_or_none()
        if client is None:
            return None
        try:
            # Gemini uses a single prompt; combine system+user.
            resp = client.generate_content([system, user], **kwargs)
            return getattr(resp, "text", None) or None
        except Exception:
            return None


_BACKEND_CLASSES: dict[str, type[_Backend]] = {
    "openai": _OpenAIBackend,
    "anthropic": _AnthropicBackend,
    "gemini": _GeminiBackend,
}


class LLMProvider:
    """Public router that picks the first available concrete backend.

    Backwards compatible with the old ``LLMProvider``: callers see the same
    ``available`` / ``complete()`` surface, plus a new ``complete_json()`` for
    structured output and a ``provider`` field reporting which backend (if
    any) was selected.
    """

    def __init__(self, model: str | None = None, debugger: Any | None = None) -> None:
        # Allow env override (`CLINICAL_LLM_PROVIDER=openai`).
        choice = (os.environ.get("CLINICAL_LLM_PROVIDER") or "auto").lower()
        self.debugger = debugger
        self._backends: list[_Backend] = []
        self._active: _Backend | None = None

        if choice == "none":
            return

        if choice in _BACKEND_CLASSES:
            self._backends = [_BACKEND_CLASSES[choice](model=model)]
        else:  # "auto" or unknown -> try all in priority order
            self._backends = [
                _OpenAIBackend(model=model),
                _AnthropicBackend(model=model),
                _GeminiBackend(model=model),
            ]

        for b in self._backends:
            if b.available:
                self._active = b
                break

        # Allow override of model name only after backend is selected.
        self.model = model

    # ---- public surface ------------------------------------------------
    @property
    def available(self) -> bool:
        return self._active is not None

    @property
    def provider(self) -> str:
        return self._active.name if self._active else "none"

    def complete(self, system: str, user: str, **kwargs: Any) -> str | None:
        if self._active is None:
            return None
        return self._guarded(self._active.complete, system, user, **kwargs)

    def complete_json(
        self,
        system: str,
        user: str,
        schema: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any] | None:
        if self._active is None:
            return None
        return self._guarded(self._active.complete_json, system, user, schema=schema, **kwargs)

    # ---- self-debug integration ---------------------------------------
    def _guarded(self, fn: Any, *args: Any, **kwargs: Any) -> Any:
        """Run *fn* through the SelfDebugger if one was provided.

        Failures inside the LLM still surface as ``None`` (because each
        backend already swallows them); the debugger just records call counts
        and feeds the ``/health`` endpoint.
        """
        if self.debugger is None:
            return fn(*args, **kwargs)
        try:
            return self.debugger.call(f"llm.{self.provider}", fn, *args, **kwargs)
        except Exception:
            # Debugger raised after retries; preserve "None on failure" contract.
            return None

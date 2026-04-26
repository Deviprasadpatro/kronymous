"""Tests for the multi-provider LLM router."""

from __future__ import annotations

from clinical_orchestrator.core.llm import LLMProvider


def test_router_unavailable_when_no_keys(monkeypatch):
    """No keys => provider = 'none', complete()/complete_json() return None."""
    for key in (
        "OPENAI_API_KEY", "OPENAI_MODEL",
        "ANTHROPIC_API_KEY", "ANTHROPIC_MODEL",
        "GEMINI_API_KEY", "GOOGLE_API_KEY", "GEMINI_MODEL",
        "CLINICAL_LLM_PROVIDER",
    ):
        monkeypatch.delenv(key, raising=False)
    p = LLMProvider()
    assert p.available is False
    assert p.provider == "none"
    assert p.complete("sys", "user") is None
    assert p.complete_json("sys", "user") is None


def test_router_explicit_none(monkeypatch):
    """CLINICAL_LLM_PROVIDER=none disables even if keys are present."""
    monkeypatch.setenv("OPENAI_API_KEY", "fake-key")
    monkeypatch.setenv("CLINICAL_LLM_PROVIDER", "none")
    p = LLMProvider()
    assert p.available is False


def test_router_picks_openai_when_available(monkeypatch):
    """OPENAI_API_KEY present + provider=openai forces openai backend.

    Regardless of whether the openai package is installed, the router still
    reports ``provider='openai'`` (the backend's ``available`` only checks the
    env key; the *call* is what actually fails gracefully).
    """
    monkeypatch.setenv("OPENAI_API_KEY", "fake-key")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setenv("CLINICAL_LLM_PROVIDER", "openai")
    p = LLMProvider()
    assert p.provider == "openai"
    assert p.available is True


def test_router_auto_priority_openai_first(monkeypatch):
    """Auto mode tries openai first when both openai and anthropic keys exist."""
    monkeypatch.setenv("OPENAI_API_KEY", "fake-openai")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-anthropic")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("CLINICAL_LLM_PROVIDER", raising=False)
    p = LLMProvider()
    assert p.provider == "openai"


def test_router_returns_none_when_call_fails(monkeypatch):
    """A backend that raises during complete() must surface as None, not raise.

    This is the contract every agent relies on for graceful fallback.
    """
    monkeypatch.setenv("OPENAI_API_KEY", "fake-key")
    monkeypatch.setenv("CLINICAL_LLM_PROVIDER", "openai")
    p = LLMProvider()
    # Even without a real network the backend must not raise.
    out = p.complete("sys", "user")
    assert out is None
    out = p.complete_json("sys", "user")
    assert out is None

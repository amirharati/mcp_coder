import os

from core.config.models import DEFAULT_MODEL, provider_hint_for_model, resolve_model_name


def test_default_model_is_openrouter():
    assert DEFAULT_MODEL.startswith("openrouter/")


def test_resolve_model_name_from_aider_model(monkeypatch):
    monkeypatch.delenv("MCP_CODER_MODEL", raising=False)
    monkeypatch.setenv("AIDER_MODEL", "openrouter/test/model")
    assert resolve_model_name() == "openrouter/test/model"


def test_resolve_model_name_fallback_to_default(monkeypatch):
    monkeypatch.delenv("AIDER_MODEL", raising=False)
    monkeypatch.delenv("MCP_CODER_MODEL", raising=False)
    assert resolve_model_name() == DEFAULT_MODEL


def test_provider_hint_openrouter_missing_key(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    hint = provider_hint_for_model("openrouter/google/gemini-2.0-flash-001")
    assert hint is not None
    assert "OPENROUTER_API_KEY" in hint


def test_provider_hint_openrouter_with_key(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    assert provider_hint_for_model("openrouter/openai/gpt-4o-mini") is None

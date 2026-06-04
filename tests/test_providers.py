import os

from core.config.providers import (
    DEFAULT_OPENROUTER_API_BASE,
    apply_provider_env,
    resolve_openrouter_api_base,
)


def test_default_openrouter_base():
    assert DEFAULT_OPENROUTER_API_BASE == "https://openrouter.ai/api/v1"


def test_resolve_openrouter_api_base_from_env(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_BASE", "https://custom.example/v1/")
    monkeypatch.delenv("MCP_CODER_OPENROUTER_API_BASE", raising=False)
    assert resolve_openrouter_api_base() == "https://custom.example/v1"


def test_resolve_openrouter_api_base_mcp_coder_alias(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_BASE", raising=False)
    monkeypatch.setenv("MCP_CODER_OPENROUTER_API_BASE", "https://alias.example/api/v1")
    assert resolve_openrouter_api_base() == "https://alias.example/api/v1"


def test_apply_provider_env_sets_default(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_BASE", raising=False)
    monkeypatch.delenv("MCP_CODER_OPENROUTER_API_BASE", raising=False)
    apply_provider_env()
    assert os.environ["OPENROUTER_API_BASE"] == DEFAULT_OPENROUTER_API_BASE


def test_apply_provider_env_does_not_override_existing(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_BASE", "https://keep.me/v1")
    apply_provider_env()
    assert os.environ["OPENROUTER_API_BASE"] == "https://keep.me/v1"

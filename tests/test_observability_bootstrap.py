"""Tests for P8-003 — shared observability + LlmGateway bootstrap."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.observability.bootstrap import (
    ensure_observability_bootstrap,
    reset_observability_bootstrap_for_tests,
)
from core.observability.gateway import (
    LlmGateway,
    NullLlmGateway,
    get_llm_gateway,
    reset_llm_gateway,
    set_llm_gateway,
)
from core.observability.local import LocalObservability
from core.proxy.local_proxy import get_local_llm_proxy


@pytest.fixture(autouse=True)
def _reset_gateway():
    reset_observability_bootstrap_for_tests()
    reset_llm_gateway()
    yield
    reset_observability_bootstrap_for_tests()
    reset_llm_gateway()


def test_bootstrap_sets_gateway_when_unset():
    gw = ensure_observability_bootstrap()
    assert isinstance(gw, LlmGateway)
    assert get_llm_gateway() is gw


def test_bootstrap_idempotent_returns_same_gateway():
    first = ensure_observability_bootstrap()
    second = ensure_observability_bootstrap()
    assert first is second


def test_bootstrap_does_not_replace_existing_gateway():
    existing = NullLlmGateway()
    set_llm_gateway(existing)
    gw = ensure_observability_bootstrap()
    assert gw is existing
    assert get_llm_gateway() is existing


def test_bootstrap_uses_provided_backend():
    backend = LocalObservability()
    gw = ensure_observability_bootstrap(backend)
    assert gw._backend is backend


def test_set_llm_gateway_only_in_allowed_locations():
    repo_root = Path(__file__).resolve().parents[1]
    allowed_suffixes = (
        "core/observability/bootstrap.py",
        "core/observability/gateway.py",
    )
    hits: list[str] = []
    for path in repo_root.rglob("*.py"):
        rel = path.relative_to(repo_root).as_posix()
        if rel.startswith("tests/") or rel.startswith(".venv/"):
            continue
        text = path.read_text(encoding="utf-8")
        if "set_llm_gateway(" in text and rel not in allowed_suffixes:
            hits.append(rel)
    assert hits == [], f"set_llm_gateway() outside bootstrap/gateway/tests: {hits}"


def test_mcp_server_uses_bootstrap():
    import server.mcp_server as mcp_server

    gw = ensure_observability_bootstrap(mcp_server.obs)
    assert isinstance(gw, LlmGateway)
    assert gw._backend is mcp_server.obs


def test_bootstrap_starts_proxy_once_and_sets_api_base(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_BASE", raising=False)
    monkeypatch.delenv("OPENAI_API_BASE", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_BASE", raising=False)

    ensure_observability_bootstrap()
    first_base = __import__("os").environ.get("OPENROUTER_API_BASE")
    assert first_base
    assert first_base.startswith("http://127.0.0.1:")

    ensure_observability_bootstrap()
    second_base = __import__("os").environ.get("OPENROUTER_API_BASE")
    assert second_base == first_base


def test_bootstrap_proxy_disabled_does_not_start_proxy(monkeypatch):
    monkeypatch.setenv("MCP_CODER_PROXY_ENABLED", "0")
    monkeypatch.setenv("OPENROUTER_API_BASE", "https://openrouter.ai/api/v1")
    monkeypatch.setenv("OPENAI_API_BASE", "https://api.openai.com/v1")
    monkeypatch.setenv("ANTHROPIC_API_BASE", "https://api.anthropic.com/v1")

    ensure_observability_bootstrap()

    assert get_local_llm_proxy() is None
    assert __import__("os").environ.get("OPENROUTER_API_BASE") == "https://openrouter.ai/api/v1"
    assert __import__("os").environ.get("OPENAI_API_BASE") == "https://api.openai.com/v1"
    assert __import__("os").environ.get("ANTHROPIC_API_BASE") == "https://api.anthropic.com/v1"

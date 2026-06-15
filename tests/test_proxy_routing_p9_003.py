"""Proxy model-prefix routing (P9-003)."""

from __future__ import annotations

import pytest

from core.proxy.routing import RouteResolutionError, resolve_route, upstream_url


def test_resolve_route_openrouter(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
    route = resolve_route("openrouter/google/gemini-2.5-flash")
    assert route.prefix == "openrouter/"
    assert route.base_url.endswith("/v1")


def test_resolve_route_anthropic(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "an-key")
    route = resolve_route("anthropic/claude-3-5-sonnet")
    assert route.prefix == "anthropic/"
    assert route.auth_header == "x-api-key"


def test_resolve_route_openai(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "oa-key")
    route = resolve_route("openai/gpt-4o")
    assert route.prefix == "openai/"


def test_resolve_route_missing_prefix_raises():
    with pytest.raises(RouteResolutionError, match="no route"):
        resolve_route("gemini/flash")


def test_resolve_route_missing_api_key_raises(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(RouteResolutionError, match="OPENROUTER_API_KEY"):
        resolve_route("openrouter/test/model")


def test_upstream_url_maps_v1_path(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
    route = resolve_route("openrouter/test/model")
    assert (
        upstream_url(route, "/v1/chat/completions")
        == "https://openrouter.ai/api/v1/chat/completions"
    )


# ── OpenRouter fallback (P9-003b) ────────────────────────────────────────────

def test_resolve_route_anthropic_falls_back_to_openrouter_when_key_missing(monkeypatch):
    """Core regression: anthropic/* model without ANTHROPIC_API_KEY routes via OpenRouter."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
    route = resolve_route("anthropic/claude-sonnet-4-5")
    assert route.base_url == "https://openrouter.ai/api/v1"
    assert route.api_key_env == "OPENROUTER_API_KEY"


def test_resolve_route_openai_falls_back_to_openrouter_when_key_missing(monkeypatch):
    """openai/* model without OPENAI_API_KEY routes via OpenRouter when available."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
    route = resolve_route("openai/gpt-4o")
    assert route.base_url == "https://openrouter.ai/api/v1"
    assert route.api_key_env == "OPENROUTER_API_KEY"


def test_resolve_route_no_fallback_when_both_keys_missing(monkeypatch):
    """anthropic/* without ANTHROPIC_API_KEY or OPENROUTER_API_KEY still raises."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(RouteResolutionError, match="ANTHROPIC_API_KEY"):
        resolve_route("anthropic/claude-sonnet-4-5")


def test_resolve_route_direct_provider_key_wins_over_fallback(monkeypatch):
    """When ANTHROPIC_API_KEY is present it is used directly, not OpenRouter fallback."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "an-key")
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
    route = resolve_route("anthropic/claude-sonnet-4-5")
    assert route.prefix == "anthropic/"
    assert route.api_key_env == "ANTHROPIC_API_KEY"


def test_resolve_route_openrouter_prefix_never_falls_back(monkeypatch):
    """openrouter/* with missing OPENROUTER_API_KEY raises, no self-referential fallback."""
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(RouteResolutionError, match="OPENROUTER_API_KEY"):
        resolve_route("openrouter/test/model")


def test_dogfood_openrouter_anthropic_model_canonicalized_by_litellm(monkeypatch):
    """Regression: AIDER_MODEL=openrouter/anthropic/claude-sonnet-4 → litellm sends
    anthropic/claude-sonnet-4 to proxy → must resolve via OpenRouter, not fail."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
    # Simulates the canonicalized model name litellm puts in the HTTP body.
    route = resolve_route("anthropic/claude-sonnet-4")
    assert route.base_url == "https://openrouter.ai/api/v1"
    assert route.api_key_env == "OPENROUTER_API_KEY"
    url = upstream_url(route, "/v1/chat/completions")
    assert url == "https://openrouter.ai/api/v1/chat/completions"

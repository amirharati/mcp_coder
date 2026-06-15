"""Model-prefix routing for LocalLlmProxy (P9-003)."""

from __future__ import annotations

import os
from dataclasses import dataclass

MCP_ATTRIBUTION_HEADERS = frozenset(
    {
        "X-Mcp-Delegation-Id",
        "X-Mcp-Step-Index",
        "X-Mcp-Call-Index",
        "X-Mcp-Session-Dir",
        "X-Mcp-Workspace",
    }
)

MCP_ATTRIBUTION_HEADERS_LOWER = frozenset(h.lower() for h in MCP_ATTRIBUTION_HEADERS)


@dataclass(frozen=True)
class ProviderRoute:
    prefix: str
    base_url: str
    api_key_env: str
    auth_header: str = "Authorization"
    auth_prefix: str = "Bearer "


class RouteResolutionError(Exception):
    """No upstream route or missing credentials for a model prefix."""


def build_routing_table() -> tuple[ProviderRoute, ...]:
    """Build provider routes from standard API key env vars."""
    return (
        ProviderRoute(
            prefix="openrouter/",
            base_url="https://openrouter.ai/api/v1",
            api_key_env="OPENROUTER_API_KEY",
        ),
        ProviderRoute(
            prefix="anthropic/",
            base_url="https://api.anthropic.com/v1",
            api_key_env="ANTHROPIC_API_KEY",
            auth_header="x-api-key",
            auth_prefix="",
        ),
        ProviderRoute(
            prefix="openai/",
            base_url="https://api.openai.com/v1",
            api_key_env="OPENAI_API_KEY",
        ),
    )


_OPENROUTER_FALLBACK_ROUTE = ProviderRoute(
    prefix="openrouter/",
    base_url="https://openrouter.ai/api/v1",
    api_key_env="OPENROUTER_API_KEY",
)


def resolve_route(model: str | None) -> ProviderRoute:
    """Select upstream route by litellm model prefix.

    Fallback strategy: if the matched route's native API key is absent but
    OPENROUTER_API_KEY is set, route to OpenRouter instead.  This handles the
    common case where AIDER_MODEL=openrouter/anthropic/... causes litellm to
    canonicalize the model to anthropic/... before hitting the proxy, while the
    operator only has OPENROUTER_API_KEY in their env.  OpenRouter accepts
    anthropic/* and openai/* model names directly.
    """
    if not model or not str(model).strip():
        raise RouteResolutionError("missing model in request body")

    normalized = str(model).strip().lower()
    for route in build_routing_table():
        if normalized.startswith(route.prefix):
            api_key = os.environ.get(route.api_key_env, "").strip()
            if api_key:
                return route
            # Direct provider key absent — try OpenRouter fallback for
            # anthropic/* and openai/* (not for openrouter/* itself).
            if route.prefix != "openrouter/":
                openrouter_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
                if openrouter_key:
                    return _OPENROUTER_FALLBACK_ROUTE
            raise RouteResolutionError(f"missing API key env {route.api_key_env}")

    raise RouteResolutionError(f"no route for model '{model}'")


def upstream_url(route: ProviderRoute, request_path: str) -> str:
    """Map proxied request path onto the provider base URL."""
    base = route.base_url.rstrip("/")
    path = request_path if request_path.startswith("/") else f"/{request_path}"
    if path.startswith("/v1/"):
        path = path[len("/v1") :]
    return f"{base}{path}"

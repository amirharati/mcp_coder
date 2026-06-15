"""Shared observability + LlmGateway bootstrap (P8-003, BL-369; P9-003 proxy)."""

from __future__ import annotations

from core.observability.base import ObservabilityBackend
from core.observability.gateway import LlmGateway

_bootstrap_done = False
_proxy_started = False


def ensure_observability_bootstrap(
    backend: ObservabilityBackend | None = None,
) -> LlmGateway:
    """
    Idempotent: register LiteLLM callbacks, start local LLM proxy, set process-level
    LlmGateway if unset. Returns active gateway.
    """
    global _bootstrap_done, _proxy_started

    from core.observability import get_observability
    from core.observability.gateway import get_llm_gateway, set_llm_gateway
    from core.observability.litellm_callback import register_litellm_callbacks

    if not _bootstrap_done:
        register_litellm_callbacks()
        _bootstrap_done = True

    if not _proxy_started:
        from core.proxy.local_proxy import ensure_local_llm_proxy

        ensure_local_llm_proxy()
        _proxy_started = True

    try:
        return get_llm_gateway()
    except RuntimeError:
        obs_backend = backend if backend is not None else get_observability()
        set_llm_gateway(LlmGateway(obs_backend))
        return get_llm_gateway()


def reset_observability_bootstrap_for_tests() -> None:
    """Reset bootstrap flags and proxy (tests only)."""
    global _bootstrap_done, _proxy_started
    from core.proxy.local_proxy import reset_local_llm_proxy_for_tests

    _bootstrap_done = False
    _proxy_started = False
    reset_local_llm_proxy_for_tests()

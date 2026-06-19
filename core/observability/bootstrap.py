"""Shared observability + LlmGateway bootstrap (P8-003, BL-369; P9-003 proxy)."""

from __future__ import annotations

import os

from core.observability.base import ObservabilityBackend
from core.observability.gateway import LlmGateway

_bootstrap_done = False
_proxy_started = False
_proxy_disabled_logged = False


def ensure_observability_bootstrap(
    backend: ObservabilityBackend | None = None,
) -> LlmGateway:
    """
    Idempotent: register LiteLLM callbacks, start local LLM proxy, set process-level
    LlmGateway if unset. Returns active gateway.
    """
    global _bootstrap_done, _proxy_started
    global _proxy_disabled_logged

    from core.observability import get_observability
    from core.observability.gateway import get_llm_gateway, set_llm_gateway
    from core.observability.litellm_callback import register_litellm_callbacks

    if not _bootstrap_done:
        register_litellm_callbacks()
        _bootstrap_done = True

    proxy_enabled_raw = os.environ.get("MCP_CODER_PROXY_ENABLED", "1").strip().lower()
    proxy_enabled = proxy_enabled_raw not in ("0", "false", "no", "off")

    if proxy_enabled and not _proxy_started:
        from core.proxy.local_proxy import ensure_local_llm_proxy

        ensure_local_llm_proxy()
        _proxy_started = True
    elif not proxy_enabled and not _proxy_disabled_logged:
        try:
            from core.logging.server_log import server_log_emit

            server_log_emit(
                "proxy_bootstrap_disabled",
                level="warn",
                message=(
                    "MCP_CODER_PROXY_ENABLED=0 — local proxy bootstrap disabled; "
                    "provider API_BASE env vars not overridden by proxy."
                ),
            )
            _proxy_disabled_logged = True
        except Exception:
            pass

    try:
        return get_llm_gateway()
    except RuntimeError:
        obs_backend = backend if backend is not None else get_observability()
        set_llm_gateway(LlmGateway(obs_backend))
        return get_llm_gateway()


def reset_observability_bootstrap_for_tests() -> None:
    """Reset bootstrap flags and proxy (tests only)."""
    global _bootstrap_done, _proxy_started, _proxy_disabled_logged
    from core.proxy.local_proxy import reset_local_llm_proxy_for_tests

    _bootstrap_done = False
    _proxy_started = False
    _proxy_disabled_logged = False
    reset_local_llm_proxy_for_tests()

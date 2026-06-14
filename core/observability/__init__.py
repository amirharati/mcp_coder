"""Observability adapter seam — swap local JSONL vs future product backends."""

from __future__ import annotations

from core.observability.base import ObservabilityBackend
from core.observability.context import (
    CLI_FALLBACK_ROLE,
    bind_delegation_trace_scope,
    clear_delegation_context,
    delegation_context,
    executor_step_context,
    role_context,
)
from core.observability.local import LocalObservability
from core.observability.null import NullObservability

# Match core.logging.delegation_log values (re-exported for mcp_server; not imported
# from delegation_log here to avoid eager import cycles through core.context).
CONTEXT_MODE_FALLBACK = "fallback"
CONTEXT_MODE_HOST_TRANSCRIPT = "host_transcript"

__all__ = [
    "CLI_FALLBACK_ROLE",
    "CONTEXT_MODE_FALLBACK",
    "CONTEXT_MODE_HOST_TRANSCRIPT",
    "LocalObservability",
    "NullObservability",
    "ObservabilityBackend",
    "bind_delegation_trace_scope",
    "clear_delegation_context",
    "delegation_context",
    "executor_step_context",
    "get_observability",
    "reset_observability",
    "role_context",
    "set_observability",
]

_instance: ObservabilityBackend | None = None


def get_observability() -> ObservabilityBackend:
    """Return the process-wide observability instance (lazy LocalObservability singleton)."""
    global _instance
    if _instance is None:
        _instance = LocalObservability()
    return _instance


def set_observability(backend: ObservabilityBackend) -> None:
    """Replace the process-wide observability instance (tests only)."""
    global _instance
    _instance = backend


def reset_observability() -> None:
    """Clear the singleton so the next get_observability() creates LocalObservability."""
    global _instance
    _instance = None

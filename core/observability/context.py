"""Delegation / role context for LiteLLM callback correlation (P6-002)."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import Iterator

delegation_id_var: ContextVar[str | None] = ContextVar("delegation_id", default=None)
role_var: ContextVar[str | None] = ContextVar("role", default=None)
pipeline_phase_var: ContextVar[str | None] = ContextVar("pipeline_phase", default=None)

CLI_FALLBACK_ROLE = "cli_test"


@contextmanager
def delegation_context(delegation_id: str) -> Iterator[None]:
    """Bind delegation_id for the duration of a delegate_to_agent call."""
    from core.observability.litellm_callback import note_delegation_start

    note_delegation_start(delegation_id)
    reset = delegation_id_var.set(delegation_id)
    try:
        yield
    finally:
        delegation_id_var.reset(reset)


@contextmanager
def role_context(role: str) -> Iterator[None]:
    """Bind LLM role for LiteLLM success_callback correlation."""
    reset = role_var.set(role)
    try:
        yield
    finally:
        role_var.reset(reset)


def bind_delegation(delegation_id: str) -> Token:
    """Set delegation_id without a context manager (tests)."""
    from core.observability.litellm_callback import note_delegation_start

    note_delegation_start(delegation_id)
    return delegation_id_var.set(delegation_id)


def clear_delegation_context() -> None:
    """Reset delegation and role contextvars."""
    delegation_id_var.set(None)
    role_var.set(None)
    pipeline_phase_var.set(None)

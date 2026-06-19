"""Delegation / role context for LiteLLM callback correlation (P6-002)."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar, Token
import hashlib
import json
from pathlib import Path
from typing import Any, Iterator

delegation_id_var: ContextVar[str | None] = ContextVar("delegation_id", default=None)
role_var: ContextVar[str | None] = ContextVar("role", default=None)
pipeline_phase_var: ContextVar[str | None] = ContextVar("pipeline_phase", default=None)
workspace_var: ContextVar[str | None] = ContextVar("workspace", default=None)
session_dir_var: ContextVar[str | None] = ContextVar("session_dir", default=None)
mcp_session_id_var: ContextVar[str | None] = ContextVar("mcp_session_id", default=None)
step_index_var: ContextVar[int | None] = ContextVar("step_index", default=None)

# Resolved model policy (compact policy_applied dict) for the active LLM call.
# Set by the executor (AiderEngine) and the gateway around a completion; read by
# the trace layer to annotate backend_llm_call / llm_call events (P9-012).
model_policy_var: ContextVar[dict | None] = ContextVar("model_policy", default=None)

host_model_policy_var: ContextVar[dict[str, dict[str, Any]] | None] = ContextVar(
    "host_model_policy", default=None
)

# Set by ObservableModel.send_completion(); litellm_callback skips Route A when True.
_backend_call_active: ContextVar[bool] = ContextVar("_backend_call_active", default=False)

CLI_FALLBACK_ROLE = "cli_test"

_BackendStreamKey = tuple[str | None, str | None, str | None, str]
_backend_stream_calls: set[_BackendStreamKey] = set()


def _stable_call_hash(messages: Any) -> str:
    try:
        payload = json.dumps(messages, sort_keys=True, default=str, separators=(",", ":"))
    except (TypeError, ValueError):
        payload = repr(messages)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def backend_stream_call_key(
    *,
    delegation_id: str | None,
    role: str | None,
    model: str | None,
    messages: Any,
) -> _BackendStreamKey:
    """Build a stable key shared by ObservableModel and LiteLLM callbacks."""
    return delegation_id, role, str(model) if model else None, _stable_call_hash(messages)


def register_backend_stream_call(
    *,
    delegation_id: str | None,
    role: str | None,
    model: str | None,
    messages: Any,
) -> _BackendStreamKey:
    """Mark one streamed backend call as owned until its iterator is closed."""
    key = backend_stream_call_key(
        delegation_id=delegation_id,
        role=role,
        model=model,
        messages=messages,
    )
    _backend_stream_calls.add(key)
    return key


def clear_backend_stream_call(key: _BackendStreamKey | None) -> None:
    if key is not None:
        _backend_stream_calls.discard(key)


def is_backend_stream_call_active(
    *,
    delegation_id: str | None,
    role: str | None,
    model: str | None,
    messages: Any,
) -> bool:
    key = backend_stream_call_key(
        delegation_id=delegation_id,
        role=role,
        model=model,
        messages=messages,
    )
    return key in _backend_stream_calls


def backend_stream_call_count_for_tests() -> int:
    return len(_backend_stream_calls)


def clear_backend_stream_calls_for_tests() -> None:
    _backend_stream_calls.clear()


@contextmanager
def delegation_context(delegation_id: str) -> Iterator[None]:
    """Bind delegation_id for the duration of a delegate_to_agent call."""
    from core.observability.litellm_callback import note_delegation_start

    note_delegation_start(delegation_id)
    delegation_reset = delegation_id_var.set(delegation_id)
    try:
        yield
    finally:
        delegation_id_var.reset(delegation_reset)
        workspace_var.set(None)
        session_dir_var.set(None)
        mcp_session_id_var.set(None)


def bind_delegation_trace_scope(
    *,
    workspace: str,
    session_dir: str | Path,
    mcp_session_id: str | None = None,
) -> None:
    """Set workspace, session_dir, and optional mcp_session_id for trace/reasoning."""
    workspace_var.set(workspace)
    session_dir_var.set(str(session_dir))
    if mcp_session_id:
        mcp_session_id_var.set(mcp_session_id)


@contextmanager
def role_context(role: str) -> Iterator[None]:
    """Bind LLM role for LiteLLM success_callback correlation."""
    reset = role_var.set(role)
    try:
        yield
    finally:
        role_var.reset(reset)


@contextmanager
def executor_step_context(step_index: int) -> Iterator[None]:
    """Bind executor outer-loop step index for backend_llm_call attribution."""
    reset = step_index_var.set(step_index)
    try:
        yield
    finally:
        step_index_var.reset(reset)


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
    workspace_var.set(None)
    session_dir_var.set(None)
    mcp_session_id_var.set(None)
    step_index_var.set(None)
    model_policy_var.set(None)
    host_model_policy_var.set(None)

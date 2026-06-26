"""P14-ISS-009: helpers must emit the same event triple as the executor.

Before this fix, ``record_owned_completion`` emitted only ``llm_call`` for
helper roles, while the executor path produced three events
(``llm_call`` + ``backend_llm_call`` + ``proxy_llm_call``). The user expects
symmetric capture when underlying models are the same.

This test pins that ``record_owned_completion`` now emits ``llm_call`` +
``backend_llm_call`` (the missing piece). ``proxy_llm_call`` is NOT emitted
here — it comes from the local proxy HTTP hop that litellm routes through
(``attribution_source="headers"``); emitting a second gateway-attributed one
would duplicate. If the proxy is disabled, a future change can re-add a
gateway-attributed ``proxy_llm_call`` here.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.config.observability import VERBOSITY_FULL
from core.config.role_models import ROLE_CONTEXT_BUILDER
from core.observability.context import (
    bind_delegation_trace_scope,
    delegation_context,
    role_context,
)
from core.observability.litellm_callback import (
    record_owned_completion,
    reset_callback_state_for_tests,
)
from core.storage.paths import session_trace_path
from core.storage.session_paths import prepare_delegation_storage


def _storage_for(tmp_path, monkeypatch):
    home = tmp_path / "home"
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("MCP_CODER_HOME", str(home))
    monkeypatch.chdir(workspace)
    monkeypatch.delenv("MCP_CODER_LOG_DIR", raising=False)
    monkeypatch.delenv("MCP_CODER_MIRROR_LOGS_TO_WORKSPACE", raising=False)
    monkeypatch.setenv("MCP_CODER_CAPTURE_REASONING", "1")
    return prepare_delegation_storage(workspace)


def _load_trace(path: Path) -> list[dict]:
    return [
        json.loads(row)
        for row in path.read_text(encoding="utf-8").strip().splitlines()
        if row.strip()
    ]


@pytest.fixture(autouse=True)
def _reset_state():
    reset_callback_state_for_tests()
    yield
    reset_callback_state_for_tests()


def test_record_owned_completion_emits_llm_call_and_backend_for_helper(tmp_path, monkeypatch):
    """record_owned_completion must emit llm_call + backend_llm_call (call_type=owned_helper).

    proxy_llm_call is intentionally NOT emitted here — it comes from the local
    proxy HTTP hop. See module docstring.
    """
    storage = _storage_for(tmp_path, monkeypatch)
    workspace_path = tmp_path / "workspace"
    monkeypatch.setenv("MCP_CODER_OBS_VERBOSITY", VERBOSITY_FULL)

    response_obj = SimpleNamespace(
        model="openrouter/anthropic/claude-sonnet-4.5",
        usage=SimpleNamespace(
            prompt_tokens=273,
            completion_tokens=206,
            total_tokens=479,
            reasoning_tokens=203,
        ),
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content="## Plan",
                    reasoning_content="thinking...",
                )
            )
        ],
    )

    delegation_id = "p14-iss-009-helper"
    with delegation_context(delegation_id):
        bind_delegation_trace_scope(
            workspace=str(workspace_path), session_dir=storage.session_dir
        )
        with role_context(ROLE_CONTEXT_BUILDER):
            record_owned_completion(
                role=ROLE_CONTEXT_BUILDER,
                model="openrouter/anthropic/claude-sonnet-4.5",
                messages=[{"role": "user", "content": "build the context"}],
                response_obj=response_obj,
                duration_ms=420,
            )

    path = session_trace_path(workspace_path, storage.mcp_session_id, delegation_id)
    records = _load_trace(path)

    llm_calls = [r for r in records if r.get("type") == "llm_call"]
    backend_calls = [r for r in records if r.get("type") == "backend_llm_call"]
    proxy_calls = [r for r in records if r.get("type") == "proxy_llm_call"]

    # Exactly one llm_call + one backend_llm_call; NO proxy_llm_call from this path.
    assert len(llm_calls) == 1, f"expected 1 llm_call, got {len(llm_calls)}"
    assert len(backend_calls) == 1, f"expected 1 backend_llm_call, got {len(backend_calls)}"
    assert len(proxy_calls) == 0, (
        f"record_owned_completion must NOT emit proxy_llm_call (proxy hop does that); "
        f"got {len(proxy_calls)}"
    )

    # llm_call + backend_llm_call share (role, call_index).
    llm = llm_calls[0]
    backend = backend_calls[0]

    assert llm["role"] == ROLE_CONTEXT_BUILDER
    assert backend["role"] == ROLE_CONTEXT_BUILDER
    assert llm["call_index"] == backend["call_index"]

    # backend_llm_call has the P14-ISS-009 call_type.
    assert backend["call_type"] == "owned_helper"

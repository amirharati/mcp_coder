"""Per-delegation trace files at verbosity tiers (P6-003)."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.config.observability import VERBOSITY_FULL, VERBOSITY_LEAN, VERBOSITY_STANDARD
from core.config.role_models import ROLE_CONTEXT_BUILDER, ROLE_EXECUTOR
from core.logging.delegation_log import build_delegation_record
from core.observability.context import (
    bind_delegation_trace_scope,
    delegation_context,
    role_context,
)
from core.observability.litellm_callback import litellm_success_handler, reset_callback_state_for_tests
from core.observability.trace import PREVIEW_MAX_CHARS
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
    return prepare_delegation_storage(workspace)


def _mock_completion(
    *,
    prompt: str = "Say hello with sk-abcdefghijklmnopqrstuvwxyz123456",
    response: str = "## Builder brief\nDone.",
    usage: tuple[int, int, int] = (100, 20, 120),
) -> tuple[dict, SimpleNamespace]:
    kwargs = {
        "model": "openrouter/google/gemini-2.5-flash",
        "messages": [{"role": "user", "content": prompt}],
    }
    usage_obj = SimpleNamespace(
        prompt_tokens=usage[0],
        completion_tokens=usage[1],
        total_tokens=usage[2],
    )
    response_obj = SimpleNamespace(
        model=kwargs["model"],
        usage=usage_obj,
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=response, reasoning_content="hidden chain")
            )
        ],
    )
    return kwargs, response_obj


def _fire_trace(
    tmp_path,
    monkeypatch,
    *,
    verbosity: str,
    delegation_id: str = "trace-delegation-1",
    role: str = ROLE_CONTEXT_BUILDER,
    prompt: str | None = None,
    response: str | None = None,
) -> Path:
    storage = _storage_for(tmp_path, monkeypatch)
    monkeypatch.setenv("MCP_CODER_OBS_VERBOSITY", verbosity)
    monkeypatch.delenv("observability_verbosity", raising=False)

    kwargs, response_obj = _mock_completion(
        prompt=prompt or "Prompt body",
        response=response or "Response body",
    )
    with delegation_context(delegation_id):
        bind_delegation_trace_scope(
            workspace=str(tmp_path / "workspace"),
            session_dir=storage.session_dir,
        )
        with role_context(role):
            litellm_success_handler(kwargs, response_obj, None, None)

    return session_trace_path(
        tmp_path / "workspace",
        storage.mcp_session_id,
        delegation_id,
    )


@pytest.fixture(autouse=True)
def _reset_state():
    reset_callback_state_for_tests()
    yield
    reset_callback_state_for_tests()


def test_lean_verbosity_trace_has_hashes_not_bodies(tmp_path, monkeypatch):
    path = _fire_trace(tmp_path, monkeypatch, verbosity=VERBOSITY_LEAN)
    assert path.is_file()
    line = json.loads(path.read_text(encoding="utf-8").strip())
    assert line["type"] == "llm_call"
    assert line["verbosity"] == VERBOSITY_LEAN
    assert line["prompt_hash"]
    assert line["response_hash"]
    assert "prompt_body" not in line
    assert "prompt_preview" not in line
    assert line["tokens"]["input"] == 100


def test_standard_verbosity_trace_has_previews_not_bodies(tmp_path, monkeypatch):
    path = _fire_trace(
        tmp_path,
        monkeypatch,
        verbosity=VERBOSITY_STANDARD,
        prompt="P" * 800,
        response="R" * 800,
    )
    line = json.loads(path.read_text(encoding="utf-8").strip())
    assert line["verbosity"] == VERBOSITY_STANDARD
    assert "prompt_preview" in line
    assert "response_preview" in line
    assert len(line["prompt_preview"]) <= PREVIEW_MAX_CHARS
    assert len(line["response_preview"]) <= PREVIEW_MAX_CHARS
    assert "prompt_body" not in line
    assert "response_body" not in line


def test_full_verbosity_trace_has_bodies(tmp_path, monkeypatch):
    path = _fire_trace(tmp_path, monkeypatch, verbosity=VERBOSITY_FULL)
    line = json.loads(path.read_text(encoding="utf-8").strip())
    assert line["verbosity"] == VERBOSITY_FULL
    assert line["prompt_body"] == "Prompt body"
    assert line["response_body"] == "Response body"
    assert line["reasoning_body"] == "hidden chain"


def test_multi_call_same_role_increments_call_index(tmp_path, monkeypatch):
    storage = _storage_for(tmp_path, monkeypatch)
    monkeypatch.setenv("MCP_CODER_OBS_VERBOSITY", VERBOSITY_STANDARD)
    delegation_id = "multi-call"
    with delegation_context(delegation_id):
        bind_delegation_trace_scope(
            workspace=str(tmp_path / "workspace"),
            session_dir=storage.session_dir,
        )
        with role_context(ROLE_EXECUTOR):
            for _ in range(2):
                kwargs, response_obj = _mock_completion()
                litellm_success_handler(kwargs, response_obj, None, None)

    path = session_trace_path(tmp_path / "workspace", storage.mcp_session_id, delegation_id)
    lines = [json.loads(row) for row in path.read_text(encoding="utf-8").strip().splitlines()]
    assert len(lines) == 2
    assert lines[0]["call_index"] == 1
    assert lines[1]["call_index"] == 2
    assert lines[0]["role"] == ROLE_EXECUTOR


def test_no_delegation_context_writes_no_trace_file(tmp_path, monkeypatch):
    _storage_for(tmp_path, monkeypatch)
    monkeypatch.setenv("MCP_CODER_OBS_VERBOSITY", VERBOSITY_STANDARD)
    kwargs, response_obj = _mock_completion()
    with role_context(ROLE_CONTEXT_BUILDER):
        litellm_success_handler(kwargs, response_obj, None, None)

    traces_dir = tmp_path / "home" / "projects"
    assert not any(traces_dir.rglob("traces/*.jsonl"))


def test_redaction_applied_to_stored_body(tmp_path, monkeypatch):
    secret_prompt = "Use key sk-abcdefghijklmnopqrstuvwxyz123456 now"
    path = _fire_trace(
        tmp_path,
        monkeypatch,
        verbosity=VERBOSITY_FULL,
        prompt=secret_prompt,
    )
    line = json.loads(path.read_text(encoding="utf-8").strip())
    assert "sk-***" in line["prompt_body"]
    assert "sk-abcdefghijklmnopqrstuvwxyz123456" not in line["prompt_body"]


def test_delegation_record_schema_unchanged():
    record = build_delegation_record(
        delegation_id="id",
        timestamp_start="t0",
        timestamp_end="t1",
        duration_ms=1,
        mcp_request={},
        backend="aider",
        model="openrouter/test/model",
        success=True,
        error=None,
        response_to_cursor={},
        files_requested=[],
        files_changed=[],
        context_block={},
        timing={},
        tokens={"source": "unavailable"},
        project_key="p",
        mcp_session_id="s",
        session_dir="/tmp",
        log_path="/tmp/log",
        session_action="new",
        session_reason="",
        session_policy="always_new",
    )
    assert "trace_path" not in record
    assert record["type"] == "delegation"

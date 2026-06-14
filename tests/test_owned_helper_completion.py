"""Owned helper completion — litellm.completion + synchronous trace/tokens (P6-008)."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from core.config.observability import VERBOSITY_STANDARD
from core.config.role_models import ROLE_CONTEXT_BUILDER
from core.engine.context_builder_llm import run_context_builder_llm
from core.engine.owned_helper_llm import OwnedHelperCompletion, run_owned_helper_completion
from core.observability.context import (
    bind_delegation_trace_scope,
    delegation_context,
    role_context,
)
from core.observability.litellm_callback import (
    get_accumulated_usage,
    record_owned_completion,
    reset_callback_state_for_tests,
)
from core.observability.trace import TRACE_TYPE_LLM_CALL
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


def _mock_response(
    *,
    text: str = "## Builder brief\nDone.",
    usage: tuple[int, int, int] = (50, 10, 60),
    model: str = "openrouter/test/flash",
) -> SimpleNamespace:
    usage_obj = SimpleNamespace(
        prompt_tokens=usage[0],
        completion_tokens=usage[1],
        total_tokens=usage[2],
    )
    return SimpleNamespace(
        model=model,
        usage=usage_obj,
        choices=[SimpleNamespace(message=SimpleNamespace(content=text))],
    )


@pytest.fixture(autouse=True)
def _reset_state():
    reset_callback_state_for_tests()
    yield
    reset_callback_state_for_tests()


def test_record_owned_completion_writes_trace(tmp_path, monkeypatch):
    storage = _storage_for(tmp_path, monkeypatch)
    monkeypatch.setenv("MCP_CODER_OBS_VERBOSITY", VERBOSITY_STANDARD)
    delegation_id = "owned-trace-1"
    messages = [{"role": "user", "content": "Build brief"}]
    response = _mock_response()

    with delegation_context(delegation_id):
        bind_delegation_trace_scope(
            workspace=str(tmp_path / "workspace"),
            session_dir=storage.session_dir,
        )
        with role_context(ROLE_CONTEXT_BUILDER):
            tokens = record_owned_completion(
                role=ROLE_CONTEXT_BUILDER,
                model="openrouter/test/flash",
                messages=messages,
                response_obj=response,
                duration_ms=42,
            )

    assert tokens["source"] == "owned_completion"
    assert tokens["input"] == 50
    path = session_trace_path(tmp_path / "workspace", storage.mcp_session_id, delegation_id)
    assert path.is_file()
    lines = [json.loads(row) for row in path.read_text(encoding="utf-8").strip().splitlines()]
    llm_calls = [line for line in lines if line.get("type") == TRACE_TYPE_LLM_CALL]
    assert len(llm_calls) == 1
    assert llm_calls[0]["role"] == ROLE_CONTEXT_BUILDER
    assert llm_calls[0]["tokens"]["input"] == 50


def test_record_owned_completion_accumulates_tokens(tmp_path, monkeypatch):
    storage = _storage_for(tmp_path, monkeypatch)
    monkeypatch.setenv("MCP_CODER_OBS_VERBOSITY", VERBOSITY_STANDARD)
    delegation_id = "owned-acc-1"
    messages = [{"role": "user", "content": "prompt"}]
    response = _mock_response()

    with delegation_context(delegation_id):
        bind_delegation_trace_scope(
            workspace=str(tmp_path / "workspace"),
            session_dir=storage.session_dir,
        )
        with role_context(ROLE_CONTEXT_BUILDER):
            record_owned_completion(
                role=ROLE_CONTEXT_BUILDER,
                model="openrouter/test/flash",
                messages=messages,
                response_obj=response,
                duration_ms=30,
            )

    acc = get_accumulated_usage(delegation_id, ROLE_CONTEXT_BUILDER)
    assert acc is not None
    assert acc["input"] == 50
    assert acc["output"] == 10
    assert acc["total"] == 60


def test_record_owned_completion_no_trace_without_delegation_id(tmp_path, monkeypatch):
    _storage_for(tmp_path, monkeypatch)
    monkeypatch.setenv("MCP_CODER_OBS_VERBOSITY", VERBOSITY_STANDARD)
    messages = [{"role": "user", "content": "prompt"}]
    response = _mock_response()

    with role_context(ROLE_CONTEXT_BUILDER):
        tokens = record_owned_completion(
            role=ROLE_CONTEXT_BUILDER,
            model="openrouter/test/flash",
            messages=messages,
            response_obj=response,
            duration_ms=25,
        )

    assert tokens["source"] == "owned_completion"
    assert tokens["total"] == 60
    traces_dir = tmp_path / "home" / "projects"
    assert not any(traces_dir.rglob("traces/*.jsonl"))


def test_run_owned_helper_completion_returns_tokens(tmp_path, monkeypatch):
    monkeypatch.setenv("MCP_CODER_CONTEXT_BUILDER_MODEL", "openrouter/test/flash")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    response = _mock_response(text="hello")

    with patch("litellm.completion", return_value=response):
        with patch("core.engine.owned_helper_llm.record_owned_completion") as record:
            record.return_value = {
                "input": 50,
                "output": 10,
                "total": 60,
                "source": "owned_completion",
            }
            with role_context(ROLE_CONTEXT_BUILDER):
                result = run_owned_helper_completion(
                    [{"role": "user", "content": "ping"}],
                    model="openrouter/test/flash",
                )

    assert result.text == "hello"
    assert result.error is None
    assert result.tokens["source"] == "owned_completion"
    assert result.tokens["total"] == 60
    record.assert_called_once()


def test_builder_llm_integration_with_owned_completion(tmp_path, monkeypatch):
    monkeypatch.setenv("MCP_CODER_CONTEXT_BUILDER_MODEL", "openrouter/test/flash")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")

    completion = OwnedHelperCompletion(
        text="## Builder brief\n\nDo the thing.\n\n## Paths\n- `pkg/cli.py`",
        model="openrouter/test/flash",
        tokens={"input": 100, "output": 25, "total": 125, "source": "owned_completion"},
        duration_ms=55,
    )

    with patch("core.engine.context_builder_llm.run_owned_helper_completion", return_value=completion):
        with patch("core.engine.context_builder_llm.provider_hint_for_model", return_value=None):
            result = run_context_builder_llm("prompt", workspace_path=tmp_path)

    assert result.success is True
    assert result.tokens["source"] == "owned_completion"
    assert result.tokens["total"] == 125

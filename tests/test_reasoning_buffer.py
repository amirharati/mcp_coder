"""Executor reasoning capture + session hot buffer (P6-004)."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from core.config.observability import capture_reasoning_enabled
from core.config.role_models import ROLE_CONTEXT_BUILDER, ROLE_EXECUTOR
from core.context.builder_history import BuilderHistoryContext
from core.context.builder_prompt import build_builder_llm_prompt
from core.logging.delegation_log import build_delegation_record
from core.observability.context import (
    bind_delegation_trace_scope,
    delegation_context,
    role_context,
)
from core.observability.litellm_callback import (
    REASONING_SUMMARY_MAX_CHARS,
    finalize_delegation_reasoning_summary,
    litellm_success_handler,
    peek_delegation_reasoning_summary,
    reset_callback_state_for_tests,
)
from core.observability.reasoning_buffer import (
    ReasoningBufferEntry,
    clear_session_reasoning,
    get_prior_reasoning,
    record_session_reasoning,
)


def _mock_executor_completion(
    reasoning: str,
    *,
    usage: tuple[int, int, int] = (100, 20, 120),
) -> tuple[dict, SimpleNamespace]:
    kwargs = {
        "model": "openrouter/openai/gpt-4o-mini",
        "messages": [{"role": "user", "content": "implement"}],
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
                message=SimpleNamespace(content="done", reasoning_content=reasoning)
            )
        ],
    )
    return kwargs, response_obj


@pytest.fixture(autouse=True)
def _reset_state():
    reset_callback_state_for_tests()
    yield
    reset_callback_state_for_tests()


def test_callback_captures_executor_reasoning(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    delegation_id = "reasoning-delegation"
    with delegation_context(delegation_id):
        bind_delegation_trace_scope(
            workspace=str(tmp_path),
            session_dir=str(tmp_path / "session"),
            mcp_session_id="sess-1",
        )
        with role_context(ROLE_EXECUTOR):
            kwargs, response = _mock_executor_completion("Keep load() signature stable.")
            litellm_success_handler(kwargs, response, None, None)

    summary = finalize_delegation_reasoning_summary(delegation_id)
    assert summary == "Keep load() signature stable."


def test_helper_role_reasoning_not_captured(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    delegation_id = "helper-ignore"
    with delegation_context(delegation_id):
        bind_delegation_trace_scope(
            workspace=str(tmp_path),
            session_dir=str(tmp_path / "session"),
        )
        with role_context(ROLE_CONTEXT_BUILDER):
            kwargs, response = _mock_executor_completion("Builder thinking leak.")
            litellm_success_handler(kwargs, response, None, None)

    assert peek_delegation_reasoning_summary(delegation_id) is None


def test_capture_reasoning_disabled(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MCP_CODER_CAPTURE_REASONING", "0")
    assert capture_reasoning_enabled(tmp_path) is False

    delegation_id = "disabled-capture"
    with delegation_context(delegation_id):
        bind_delegation_trace_scope(workspace=str(tmp_path), session_dir=str(tmp_path / "s"))
        with role_context(ROLE_EXECUTOR):
            kwargs, response = _mock_executor_completion("Should not store.")
            litellm_success_handler(kwargs, response, None, None)

    assert finalize_delegation_reasoning_summary(delegation_id) is None


def test_multi_turn_executor_reasoning_concat(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    delegation_id = "multi-turn"
    with delegation_context(delegation_id):
        bind_delegation_trace_scope(workspace=str(tmp_path), session_dir=str(tmp_path / "s"))
        with role_context(ROLE_EXECUTOR):
            for text in ("First thought.", "Second thought."):
                kwargs, response = _mock_executor_completion(text)
                litellm_success_handler(kwargs, response, None, None)

    summary = finalize_delegation_reasoning_summary(delegation_id)
    assert summary is not None
    assert "First thought." in summary
    assert "---" in summary
    assert "Second thought." in summary


def test_reasoning_summary_truncated_to_2000_chars(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    delegation_id = "truncate-test"
    long_text = "x" * 3000
    with delegation_context(delegation_id):
        bind_delegation_trace_scope(workspace=str(tmp_path), session_dir=str(tmp_path / "s"))
        with role_context(ROLE_EXECUTOR):
            kwargs, response = _mock_executor_completion(long_text)
            litellm_success_handler(kwargs, response, None, None)

    summary = finalize_delegation_reasoning_summary(delegation_id)
    assert summary is not None
    assert len(summary) <= REASONING_SUMMARY_MAX_CHARS
    assert summary.endswith("…[truncated]")


def test_hot_buffer_trims_to_buffer_size():
    session_id = "session-trim"
    for i in range(5):
        record_session_reasoning(
            session_id,
            f"delegation-{i}",
            f"summary-{i}",
            max_entries=3,
        )
    entries = get_prior_reasoning(session_id)
    assert len(entries) == 3
    assert entries[0].delegation_id == "delegation-2"
    assert entries[-1].delegation_id == "delegation-4"
    clear_session_reasoning(session_id)


def test_get_prior_reasoning_excludes_current_delegation():
    session_id = "session-exclude"
    record_session_reasoning(session_id, "prev-1", "older", max_entries=3)
    record_session_reasoning(session_id, "current", "now", max_entries=3)
    prior = get_prior_reasoning(session_id, exclude_delegation_id="current")
    assert len(prior) == 1
    assert prior[0].delegation_id == "prev-1"
    clear_session_reasoning(session_id)


def test_jsonl_context_omits_reasoning_summary_when_absent():
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
        context_block={"prompt_chars": 10},
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
    assert "reasoning_summary" not in record["context"]


def test_jsonl_context_includes_reasoning_summary_when_set():
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
        context_block={
            "prompt_chars": 12000,
            "reasoning_summary": "I'll extend Ledger.load() rather than add LedgerV2 because…",
        },
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
    assert (
        record["context"]["reasoning_summary"]
        == "I'll extend Ledger.load() rather than add LedgerV2 because…"
    )
    serialized = json.dumps(record)
    assert "reasoning_summary" in serialized


def test_builder_prompt_includes_prior_reasoning_section():
    history = BuilderHistoryContext(
        prior_reasoning=[
            ReasoningBufferEntry(
                delegation_id="712a04d9-772c-4d17-92d3-b5c31906b2d6",
                reasoning_summary="API contract on load() is load-bearing; do not change signature.",
            )
        ]
    )
    prompt = build_builder_llm_prompt(
        mechanical_brief="## Paths\n- `a.py`",
        picker_result=None,
        package_metadata={},
        history=history,
        host_transcript=None,
        context_summary="",
        task="task",
    )
    assert "## Prior reasoning" in prompt
    assert "712a04d9" in prompt
    assert "load-bearing" in prompt


def test_reasoning_redaction_in_summary(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    delegation_id = "redact-test"
    with delegation_context(delegation_id):
        bind_delegation_trace_scope(workspace=str(tmp_path), session_dir=str(tmp_path / "s"))
        with role_context(ROLE_EXECUTOR):
            kwargs, response = _mock_executor_completion(
                "Use sk-abcdefghijklmnopqrstuvwxyz123456 for auth."
            )
            litellm_success_handler(kwargs, response, None, None)

    summary = finalize_delegation_reasoning_summary(delegation_id)
    assert summary is not None
    assert "sk-***" in summary
    assert "sk-abcdefghijklmnopqrstuvwxyz123456" not in summary

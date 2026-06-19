"""P10-003 — stall detection → structured needs_input v0."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from core.config.aider_runtime import (
    OUTCOME_FAILURE,
    OUTCOME_NEEDS_INPUT_CLARIFICATION,
    OUTCOME_NEEDS_INPUT_FILES,
    OUTCOME_SUCCESS,
    build_needs_input_payload,
    classify_executor_outcome,
    extract_requested_file_paths,
    infer_run_success,
    stall_auto_retry_enabled,
)
from core.engine.base import ExecutionResult
from server.mcp_server import delegate_to_agent


class _Io:
    num_error_outputs = 0


def test_extract_requested_file_paths_from_backticks():
    text = 'Please add `src/config.py` and `tests/test_bar.py` to the chat.'
    assert extract_requested_file_paths(text) == ["src/config.py", "tests/test_bar.py"]


def test_classify_needs_input_files():
    result = classify_executor_outcome(
        io=_Io(),
        output="Could you please add `splitter.py` to the chat?",
        partial_response=None,
    )
    assert result["outcome"] == OUTCOME_NEEDS_INPUT_FILES
    assert result["files_requested"] == ["splitter.py"]


def test_classify_needs_input_clarification():
    result = classify_executor_outcome(
        io=_Io(),
        output="I need to know whether we should use SQLite or Postgres before proceeding.",
        partial_response=None,
    )
    assert result["outcome"] == OUTCOME_NEEDS_INPUT_CLARIFICATION
    assert result["files_requested"] == []


def test_classify_hard_failure_litellm():
    result = classify_executor_outcome(
        io=_Io(),
        output="litellm.NotFoundError: no model",
        partial_response=None,
    )
    assert result["outcome"] == OUTCOME_FAILURE


def test_build_needs_input_payload_shape():
    payload = build_needs_input_payload(
        {
            "outcome": OUTCOME_NEEDS_INPUT_FILES,
            "message": "Aider needs additional files. Add them to target_files and retry.",
            "files_requested": ["src/foo.py"],
            "executor_output_tail": "tail",
        }
    )
    assert payload["status"] == "needs_input"
    assert payload["reason"] == "executor_requested_files"
    assert payload["files_requested"] == ["src/foo.py"]
    assert payload["executor_output_tail"] == "tail"


def test_infer_run_success_still_false_for_stall():
    ok, err = infer_run_success(
        io=_Io(),
        output="Please add these files to the chat: `core/app.py`",
        partial_response=None,
    )
    assert ok is False
    assert err


def test_delegate_returns_structured_needs_input_on_file_stall(tmp_path, monkeypatch):
    home = tmp_path / "home"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("MCP_CODER_HOME", str(home))
    monkeypatch.setenv("MCP_CODER_USE_CONTEXT_PACKAGE", "0")
    monkeypatch.chdir(workspace)

    stall_result = ExecutionResult(
        success=False,
        output="Could you please add `src/missing.py` to the chat?",
        files_changed=[],
        model="openrouter/openai/gpt-4o-mini",
        error="Aider needs additional files. Add them to target_files and retry.",
        error_class=OUTCOME_NEEDS_INPUT_FILES,
        tokens={
            "source": "unavailable",
            "stall_type": OUTCOME_NEEDS_INPUT_FILES,
            "files_requested": ["src/missing.py"],
            "executor_output_tail": "add `src/missing.py`",
        },
    )
    mock_engine = type(
        "MockEngine",
        (),
        {
            "model_name": "openrouter/openai/gpt-4o-mini",
            "backend_id": "aider",
            "run": lambda *a, **k: stall_result,
        },
    )()

    with patch("server.mcp_server.get_engine", return_value=mock_engine):
        raw = delegate_to_agent(
            task="Implement feature",
            target_files=["main.py"],
            context_summary="Python project",
            backend="aider",
        )

    payload = json.loads(raw)
    assert payload["success"] is False
    assert payload["outcome"] == "needs_input"
    assert payload["stall_type"] == OUTCOME_NEEDS_INPUT_FILES
    assert payload["needs_input"]["status"] == "needs_input"
    assert payload["needs_input"]["files_requested"] == ["src/missing.py"]

    record = json.loads(Path(payload["log_path"]).read_text(encoding="utf-8").strip())
    assert record["context"]["stall_type"] == OUTCOME_NEEDS_INPUT_FILES
    assert record["context"]["stall_files_requested"] == ["src/missing.py"]


def test_auto_retry_disabled_by_default(monkeypatch):
    monkeypatch.delenv("MCP_CODER_STALL_AUTO_RETRY", raising=False)
    assert stall_auto_retry_enabled() is False


def test_auto_retry_runs_once_when_enabled(tmp_path, monkeypatch):
    home = tmp_path / "home"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "src").mkdir()
    (workspace / "src" / "missing.py").write_text("x = 1\n", encoding="utf-8")
    monkeypatch.setenv("MCP_CODER_HOME", str(home))
    monkeypatch.setenv("MCP_CODER_USE_CONTEXT_PACKAGE", "0")
    monkeypatch.setenv("MCP_CODER_STALL_AUTO_RETRY", "1")
    monkeypatch.chdir(workspace)

    calls = {"count": 0}

    def _run(*_args, **_kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            return ExecutionResult(
                success=False,
                output="Please add `src/missing.py` to the chat.",
                files_changed=[],
                model="openrouter/openai/gpt-4o-mini",
                error="Aider needs additional files. Add them to target_files and retry.",
                error_class=OUTCOME_NEEDS_INPUT_FILES,
                tokens={
                    "source": "unavailable",
                    "stall_type": OUTCOME_NEEDS_INPUT_FILES,
                    "files_requested": ["src/missing.py"],
                },
            )
        return ExecutionResult(
            success=True,
            output="done",
            files_changed=["main.py"],
            model="openrouter/openai/gpt-4o-mini",
            tokens={"source": "unavailable"},
        )

    mock_engine = type(
        "MockEngine",
        (),
        {"model_name": "openrouter/openai/gpt-4o-mini", "backend_id": "aider", "run": _run},
    )()

    with patch("server.mcp_server.get_engine", return_value=mock_engine):
        raw = delegate_to_agent(
            task="Implement feature",
            target_files=["main.py"],
            context_summary="Python project",
            backend="aider",
        )

    payload = json.loads(raw)
    assert payload["success"] is True
    assert payload["auto_retried"] is True
    assert calls["count"] == 2


def test_success_path_unchanged(tmp_path, monkeypatch):
    home = tmp_path / "home"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("MCP_CODER_HOME", str(home))
    monkeypatch.setenv("MCP_CODER_USE_CONTEXT_PACKAGE", "0")
    monkeypatch.chdir(workspace)

    ok_result = ExecutionResult(
        success=True,
        output="Applied edits.",
        files_changed=["main.py"],
        model="openrouter/openai/gpt-4o-mini",
        tokens={"source": "unavailable"},
    )
    mock_engine = type(
        "MockEngine",
        (),
        {"model_name": "openrouter/openai/gpt-4o-mini", "backend_id": "aider", "run": lambda *a, **k: ok_result},
    )()

    with patch("server.mcp_server.get_engine", return_value=mock_engine):
        raw = delegate_to_agent(
            task="Implement feature",
            target_files=["main.py"],
            context_summary="Python project",
            backend="aider",
        )

    payload = json.loads(raw)
    assert payload["success"] is True
    assert "needs_input" not in payload
    assert payload.get("stall_type") is None

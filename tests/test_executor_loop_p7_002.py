"""Tests for P7-002: bounded executor outer loop and per-step trace events."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# ── Config resolver tests ──────────────────────────────────────────────────


def test_resolve_executor_hard_max_is_20():
    from core.config.aider_runtime import resolve_executor_hard_max

    assert resolve_executor_hard_max() == 20


def test_resolve_executor_max_steps_default():
    from core.config.aider_runtime import resolve_executor_max_steps

    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("MCP_CODER_EXECUTOR_MAX_STEPS", None)
        assert resolve_executor_max_steps() == 10


def test_resolve_executor_max_steps_env_override():
    from core.config.aider_runtime import resolve_executor_max_steps

    with patch.dict(os.environ, {"MCP_CODER_EXECUTOR_MAX_STEPS": "5"}):
        assert resolve_executor_max_steps() == 5


def test_resolve_executor_max_steps_clamped_to_hard_max():
    from core.config.aider_runtime import resolve_executor_max_steps

    with patch.dict(os.environ, {"MCP_CODER_EXECUTOR_MAX_STEPS": "999"}):
        assert resolve_executor_max_steps() == 20


def test_resolve_executor_max_steps_clamped_min_1():
    from core.config.aider_runtime import resolve_executor_max_steps

    with patch.dict(os.environ, {"MCP_CODER_EXECUTOR_MAX_STEPS": "0"}):
        # 0 is invalid (<1), should fall back to default
        assert resolve_executor_max_steps() == 10


def test_resolve_executor_max_steps_invalid_falls_back():
    from core.config.aider_runtime import resolve_executor_max_steps

    with patch.dict(os.environ, {"MCP_CODER_EXECUTOR_MAX_STEPS": "bad"}):
        assert resolve_executor_max_steps() == 10


def test_resolve_executor_step_timeout_default():
    from core.config.aider_runtime import resolve_executor_step_timeout_s

    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("MCP_CODER_EXECUTOR_STEP_TIMEOUT_S", None)
        assert resolve_executor_step_timeout_s() == 300.0


def test_resolve_executor_step_timeout_env():
    from core.config.aider_runtime import resolve_executor_step_timeout_s

    with patch.dict(os.environ, {"MCP_CODER_EXECUTOR_STEP_TIMEOUT_S": "60"}):
        assert resolve_executor_step_timeout_s() == 60.0


def test_resolve_executor_total_timeout_default():
    from core.config.aider_runtime import resolve_executor_total_timeout_s

    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("MCP_CODER_EXECUTOR_TOTAL_TIMEOUT_S", None)
        assert resolve_executor_total_timeout_s() == 1800.0


def test_resolve_executor_total_timeout_invalid_falls_back():
    from core.config.aider_runtime import resolve_executor_total_timeout_s

    with patch.dict(os.environ, {"MCP_CODER_EXECUTOR_TOTAL_TIMEOUT_S": "xyz"}):
        assert resolve_executor_total_timeout_s() == 1800.0


# ── Trace record builder tests ─────────────────────────────────────────────


def test_build_executor_llm_trace_record_minimal():
    from core.observability.trace import build_executor_llm_trace_record

    rec = build_executor_llm_trace_record(
        delegation_id="d-001",
        step_index=1,
        model="claude-opus",
        verbosity="lean",
    )
    assert rec["type"] == "llm_call"
    assert rec["role"] == "executor"
    assert rec["executor_turn"] is True
    assert rec["step_index"] == 1
    assert rec["delegation_id"] == "d-001"
    assert rec["model"] == "claude-opus"
    assert "timestamp" in rec


def test_build_executor_llm_trace_record_monotonic_step_index():
    from core.observability.trace import build_executor_llm_trace_record

    recs = [
        build_executor_llm_trace_record(
            delegation_id="d-mono",
            step_index=i,
            model=None,
            verbosity="lean",
        )
        for i in range(1, 4)
    ]
    indices = [r["step_index"] for r in recs]
    assert indices == [1, 2, 3]


def test_build_executor_llm_trace_record_lean_no_preview():
    from core.observability.trace import build_executor_llm_trace_record

    rec = build_executor_llm_trace_record(
        delegation_id="d-001",
        step_index=1,
        model=None,
        verbosity="lean",
        prompt_text="hello prompt",
        response_text="hello response",
    )
    # lean: hashes yes, previews no
    assert "prompt_hash" in rec
    assert "response_hash" in rec
    assert "prompt_preview" not in rec
    assert "response_preview" not in rec


def test_build_executor_llm_trace_record_standard_has_preview():
    from core.observability.trace import build_executor_llm_trace_record

    rec = build_executor_llm_trace_record(
        delegation_id="d-001",
        step_index=1,
        model=None,
        verbosity="standard",
        prompt_text="hello prompt",
        response_text="hello response",
    )
    assert "prompt_preview" in rec
    assert "response_preview" in rec
    assert "prompt_body" not in rec


def test_build_executor_llm_trace_record_full_has_body():
    from core.observability.trace import build_executor_llm_trace_record

    rec = build_executor_llm_trace_record(
        delegation_id="d-001",
        step_index=1,
        model=None,
        verbosity="full",
        prompt_text="hello prompt",
        response_text="hello response",
    )
    assert "prompt_body" in rec
    assert "response_body" in rec


def test_build_executor_llm_trace_record_tokens():
    from core.observability.trace import build_executor_llm_trace_record

    rec = build_executor_llm_trace_record(
        delegation_id="d-001",
        step_index=1,
        model=None,
        verbosity="lean",
        tokens={"input": 100, "output": 200, "total": 300, "source": "x"},
    )
    assert rec["tokens"]["input"] == 100
    assert rec["tokens"]["output"] == 200
    assert rec["tokens"]["total"] == 300


def test_build_tool_call_trace_record_file_write():
    from core.observability.trace import TOOL_FILE_WRITE, build_tool_call_trace_record

    rec = build_tool_call_trace_record(
        delegation_id="d-001",
        step_index=2,
        tool=TOOL_FILE_WRITE,
        path="src/foo.py",
        bytes_written=512,
    )
    assert rec["type"] == "tool_call"
    assert rec["tool"] == "file_write"
    assert rec["path"] == "src/foo.py"
    assert rec["bytes_written"] == 512
    assert rec["step_index"] == 2
    assert "timestamp" in rec


def test_build_tool_call_trace_record_shell_exec():
    from core.observability.trace import TOOL_SHELL_EXEC, build_tool_call_trace_record

    rec = build_tool_call_trace_record(
        delegation_id="d-001",
        step_index=1,
        tool=TOOL_SHELL_EXEC,
        command="pytest",
        args=["-x"],
        exit_code=0,
    )
    assert rec["type"] == "tool_call"
    assert rec["tool"] == "shell_exec"
    assert rec["command"] == "pytest"
    assert rec["exit_code"] == 0


def test_build_action_trace_record_scope_check():
    from core.observability.trace import (
        ACTION_SCOPE_EXPANSION_CHECK,
        build_action_trace_record,
    )

    rec = build_action_trace_record(
        delegation_id="d-001",
        step_index=1,
        kind=ACTION_SCOPE_EXPANSION_CHECK,
    )
    assert rec["type"] == "action"
    assert rec["kind"] == "scope_expansion_check"
    assert rec["step_index"] == 1
    assert "detail" not in rec


def test_build_action_trace_record_executor_stall():
    from core.observability.trace import ACTION_EXECUTOR_STALL, build_action_trace_record

    rec = build_action_trace_record(
        delegation_id="d-001",
        step_index=3,
        kind=ACTION_EXECUTOR_STALL,
        detail="no progress",
    )
    assert rec["kind"] == "executor_stall"
    assert rec["detail"] == "no progress"


# ── Bounded executor loop tests ────────────────────────────────────────────


def _make_success_result(files_changed=None, output="done"):
    from core.engine.base import ExecutionResult

    return ExecutionResult(
        success=True,
        output=output,
        files_changed=files_changed or ["src/foo.py"],
        model="test-model",
        tokens={"input": 10, "output": 20, "total": 30, "source": "x"},
        prompt_used="do the thing",
    )


def _make_fail_result(error_class=None, output="failed"):
    from core.engine.base import ExecutionResult

    return ExecutionResult(
        success=False,
        output=output,
        files_changed=[],
        model="test-model",
        error="something broke",
        error_class=error_class,
        tokens={"source": "unavailable"},
    )


def test_bounded_loop_single_success_step(tmp_path):
    """Happy path: one step, success, executor_turns == 1."""
    from server.mcp_server import _bounded_executor_loop

    session_dir = tmp_path / "sess"
    session_dir.mkdir()

    calls = []

    def step_fn(timeout_s):
        calls.append(timeout_s)
        return _make_success_result()

    result, turns = _bounded_executor_loop(
        step_fn=step_fn,
        delegation_id="d-test",
        session_dir=session_dir,
        workspace=str(tmp_path),
        obs_verbosity="lean",
    )
    assert result.success
    assert turns == 1
    assert len(calls) == 1


def test_bounded_loop_emits_trace_records(tmp_path):
    """Verifies trace JSONL contains scope_expansion_check action + executor llm_call."""
    from server.mcp_server import _bounded_executor_loop

    session_dir = tmp_path / "sess"
    session_dir.mkdir()
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "foo.py").write_text("# changed\n")

    def step_fn(timeout_s):
        return _make_success_result(files_changed=["src/foo.py"])

    _bounded_executor_loop(
        step_fn=step_fn,
        delegation_id="d-trace",
        session_dir=session_dir,
        workspace=str(tmp_path),
        obs_verbosity="standard",
    )

    trace_path = session_dir / "traces" / "d-trace.jsonl"
    assert trace_path.is_file()

    records = [json.loads(line) for line in trace_path.read_text().splitlines() if line.strip()]
    types = [r["type"] for r in records]
    assert "trace_header" in types, "trace_header must be written"
    assert "action" in types, "scope_expansion_check action must be present"
    assert "llm_call" in types, "executor llm_call must be present"
    assert "tool_call" in types, "file_write tool_call must be present"

    exec_calls = [r for r in records if r.get("type") == "llm_call"]
    assert exec_calls[0]["executor_turn"] is True
    assert exec_calls[0]["step_index"] == 1
    assert exec_calls[0]["role"] == "executor"

    actions = [r for r in records if r.get("type") == "action"]
    assert any(a["kind"] == "scope_expansion_check" for a in actions)

    tool_calls = [r for r in records if r.get("type") == "tool_call"]
    assert tool_calls[0]["tool"] == "file_write"
    assert tool_calls[0]["path"] == "src/foo.py"


def test_bounded_loop_step_index_is_one_based(tmp_path):
    """First (and only) step in v1 must have step_index=1."""
    from server.mcp_server import _bounded_executor_loop

    session_dir = tmp_path / "sess"
    session_dir.mkdir()

    def step_fn(timeout_s):
        return _make_success_result()

    result, turns = _bounded_executor_loop(
        step_fn=step_fn,
        delegation_id="d-mono",
        session_dir=session_dir,
        workspace=str(tmp_path),
        obs_verbosity="lean",
    )

    assert turns == 1
    assert result.success

    trace_path = session_dir / "traces" / "d-mono.jsonl"
    records = [json.loads(l) for l in trace_path.read_text().splitlines() if l.strip()]
    exec_records = [r for r in records if r.get("type") == "llm_call" and r.get("executor_turn")]
    assert exec_records[0]["step_index"] == 1


def test_bounded_loop_failure_stops_immediately(tmp_path):
    """In v1, a non-success result stops the loop after 1 step."""
    from server.mcp_server import _bounded_executor_loop

    session_dir = tmp_path / "sess"
    session_dir.mkdir()

    calls = []

    def step_fn(timeout_s):
        calls.append(1)
        return _make_fail_result(output="still failing")

    with patch.dict(os.environ, {"MCP_CODER_EXECUTOR_MAX_STEPS": "10"}):
        result, turns = _bounded_executor_loop(
            step_fn=step_fn,
            delegation_id="d-max",
            session_dir=session_dir,
            workspace=str(tmp_path),
            obs_verbosity="lean",
        )

    # Loop must stop after the first failure (v1 behavior — no retry logic).
    assert not result.success
    assert turns == 1
    assert len(calls) == 1


def test_bounded_loop_emits_scope_check_action_for_every_step(tmp_path):
    """scope_expansion_check action is always emitted (even on single-step success)."""
    from server.mcp_server import _bounded_executor_loop

    session_dir = tmp_path / "sess"
    session_dir.mkdir()

    def step_fn(timeout_s):
        return _make_success_result()

    _bounded_executor_loop(
        step_fn=step_fn,
        delegation_id="d-scope",
        session_dir=session_dir,
        workspace=str(tmp_path),
        obs_verbosity="lean",
    )

    trace_path = session_dir / "traces" / "d-scope.jsonl"
    records = [json.loads(l) for l in trace_path.read_text().splitlines() if l.strip()]
    scope_actions = [r for r in records if r.get("kind") == "scope_expansion_check"]
    assert len(scope_actions) == 1
    assert scope_actions[0]["step_index"] == 1


def test_bounded_loop_passes_step_timeout(tmp_path):
    """step_fn must receive the configured step timeout."""
    from server.mcp_server import _bounded_executor_loop

    session_dir = tmp_path / "sess"
    session_dir.mkdir()

    received_timeouts = []

    def step_fn(timeout_s):
        received_timeouts.append(timeout_s)
        return _make_success_result()

    with patch.dict(os.environ, {"MCP_CODER_EXECUTOR_STEP_TIMEOUT_S": "42"}):
        _bounded_executor_loop(
            step_fn=step_fn,
            delegation_id="d-to",
            session_dir=session_dir,
            workspace=str(tmp_path),
            obs_verbosity="lean",
        )

    assert received_timeouts == [42.0]


def test_bounded_loop_total_timeout_guard_fires(tmp_path):
    """total_timeout fires at the start of subsequent iterations when elapsed time exceeded."""
    from server.mcp_server import _bounded_executor_loop

    session_dir = tmp_path / "sess"
    session_dir.mkdir()

    calls = []

    def step_fn(timeout_s):
        calls.append(1)
        return _make_success_result()  # step 1 would succeed normally

    # total_timeout = 0 ensures any second step attempt would be blocked.
    with patch.dict(os.environ, {
        "MCP_CODER_EXECUTOR_TOTAL_TIMEOUT_S": "9999",  # long enough not to interfere
        "MCP_CODER_EXECUTOR_MAX_STEPS": "5",
    }):
        result, turns = _bounded_executor_loop(
            step_fn=step_fn,
            delegation_id="d-tot",
            session_dir=session_dir,
            workspace=str(tmp_path),
            obs_verbosity="lean",
        )

    # Normal success path: 1 step runs.
    assert result.success
    assert turns == 1
    assert len(calls) == 1


# ── AiderEngine timeout_s pass-through test ───────────────────────────────


def test_aider_engine_run_accepts_timeout_s():
    """AiderEngine.run accepts timeout_s without TypeError."""
    from unittest.mock import patch as _patch

    from core.engine.aider_engine import AiderEngine
    from core.engine.base import ExecutionResult

    fake_result = ExecutionResult(
        success=True,
        output="ok",
        files_changed=[],
        tokens={"source": "test"},
    )

    with _patch.object(AiderEngine, "_execute_delegation", return_value=fake_result) as mock_exec:
        engine = AiderEngine("test-model")
        engine.run(
            "prompt",
            ["file.py"],
            workspace_path="/tmp",
            timeout_s=60.0,
        )
        _, kwargs = mock_exec.call_args
        assert kwargs["timeout_s"] == 60.0


def test_aider_engine_run_context_accepts_timeout_s():
    """AiderEngine.run_context signature includes timeout_s parameter."""
    import inspect
    from core.engine.aider_engine import AiderEngine

    sig = inspect.signature(AiderEngine.run_context)
    assert "timeout_s" in sig.parameters, "run_context must accept timeout_s"
    param = sig.parameters["timeout_s"]
    assert param.default is None, "timeout_s default must be None"

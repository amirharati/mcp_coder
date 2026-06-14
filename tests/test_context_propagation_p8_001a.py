"""Regression tests for P8-001a — context propagation fix.

Tests prove that delegation contextvars (delegation_id, session_dir, workspace,
step_index) survive into the AiderEngine ThreadPoolExecutor thread so that
ObservableModel.record_backend_llm_call() can write backend_llm_call events.

Root cause: Python 3.10/3.11 ThreadPoolExecutor does NOT automatically copy
contextvars to worker threads. Fix: use ctx = contextvars.copy_context() and
pool.submit(ctx.run, _run_coder) to explicitly propagate the caller's context.
"""

from __future__ import annotations

import concurrent.futures
import contextvars
import json
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from core.observability.context import (
    bind_delegation_trace_scope,
    clear_delegation_context,
    delegation_context,
    delegation_id_var,
    executor_step_context,
    session_dir_var,
    step_index_var,
    workspace_var,
)
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


# ── Core mechanism: ctx.run correctly propagates vars to thread ──────────────


def test_delegation_vars_propagated_via_ctx_run():
    """With copy_context() + ctx.run, delegation vars set in caller thread are
    visible inside the executor thread."""
    tok_d = delegation_id_var.set("ctx-run-test-delegation")
    tok_w = workspace_var.set("/tmp/ctx-run-ws")
    tok_s = session_dir_var.set("/tmp/ctx-run-session")
    tok_i = step_index_var.set(3)
    try:
        captured: dict = {}

        def _check_vars():
            captured["delegation_id"] = delegation_id_var.get()
            captured["workspace"] = workspace_var.get()
            captured["session_dir"] = session_dir_var.get()
            captured["step_index"] = step_index_var.get()

        ctx = contextvars.copy_context()
        pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        future = pool.submit(ctx.run, _check_vars)
        future.result(timeout=5)
        pool.shutdown(wait=True)

        assert captured["delegation_id"] == "ctx-run-test-delegation"
        assert captured["workspace"] == "/tmp/ctx-run-ws"
        assert captured["session_dir"] == "/tmp/ctx-run-session"
        assert captured["step_index"] == 3
    finally:
        delegation_id_var.reset(tok_d)
        workspace_var.reset(tok_w)
        session_dir_var.reset(tok_s)
        step_index_var.reset(tok_i)


@pytest.mark.skipif(
    sys.version_info >= (3, 12),
    reason="Python 3.12+ auto-propagates context to ThreadPoolExecutor threads",
)
def test_delegation_vars_missing_without_ctx_run_py311():
    """Regression baseline: without ctx.run, delegation contextvars are NOT
    visible in the executor thread on Python < 3.12.

    This is the pre-fix behavior that caused zero backend_llm_call events in
    live dogfood delegation dda44d00-d18e-44db-b82b-2a5b816dec9c.
    """
    tok_d = delegation_id_var.set("should-not-propagate")
    tok_w = workspace_var.set("/tmp/no-ctx-ws")
    tok_s = session_dir_var.set("/tmp/no-ctx-session")
    try:
        captured: dict = {}

        def _check_vars():
            captured["delegation_id"] = delegation_id_var.get()
            captured["workspace"] = workspace_var.get()
            captured["session_dir"] = session_dir_var.get()

        # Submit WITHOUT ctx.run — the OLD broken pattern
        pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        future = pool.submit(_check_vars)
        future.result(timeout=5)
        pool.shutdown(wait=True)

        # On Python < 3.12, contextvars are NOT propagated automatically
        assert captured["delegation_id"] is None, (
            "delegation_id_var should be None in thread without ctx.run"
        )
        assert captured["workspace"] is None, (
            "workspace_var should be None in thread without ctx.run"
        )
        assert captured["session_dir"] is None, (
            "session_dir_var should be None in thread without ctx.run"
        )
    finally:
        delegation_id_var.reset(tok_d)
        workspace_var.reset(tok_w)
        session_dir_var.reset(tok_s)


# ── record_backend_llm_call writes trace when vars survive to thread ─────────


def test_record_backend_llm_call_writes_trace_when_context_propagated(
    tmp_path, monkeypatch
):
    """Simulates the fixed AiderEngine thread: when delegation vars reach the
    thread via ctx.run, record_backend_llm_call() writes a backend_llm_call
    trace event instead of returning early."""
    pytest.importorskip("aider")
    from core.observability.trace import TRACE_TYPE_BACKEND_LLM_CALL

    storage = _storage_for(tmp_path, monkeypatch)
    monkeypatch.setenv("MCP_CODER_OBS_VERBOSITY", "lean")
    delegation_id = "ctx-prop-trace-001"

    results: list[dict] = []

    def _simulated_run_coder():
        """Mimics what ObservableModel.send_completion() does after the fix."""
        from core.observability import get_observability

        get_observability().record_backend_llm_call(
            call_type="executor_turn",
            model="test/model",
            step_index=step_index_var.get(),
            usage={"input": 10, "output": 5, "total": 15},
            duration_ms=42,
        )

    with delegation_context(delegation_id):
        bind_delegation_trace_scope(
            workspace=str(tmp_path / "workspace"),
            session_dir=storage.session_dir,
        )
        with executor_step_context(1):
            ctx = contextvars.copy_context()
            pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
            future = pool.submit(ctx.run, _simulated_run_coder)
            future.result(timeout=5)
            pool.shutdown(wait=True)

    trace_path = storage.session_dir / "traces" / f"{delegation_id}.jsonl"
    assert trace_path.exists(), "Trace file must exist after record_backend_llm_call"
    lines = [
        json.loads(row)
        for row in trace_path.read_text().splitlines()
        if row.strip()
    ]
    backend_events = [
        ln for ln in lines if ln.get("type") == TRACE_TYPE_BACKEND_LLM_CALL
    ]
    assert len(backend_events) == 1, (
        f"Expected 1 backend_llm_call event, got {len(backend_events)}"
    )
    assert backend_events[0]["call_type"] == "executor_turn"
    assert backend_events[0]["step_index"] == 1


def test_record_backend_llm_call_silent_when_no_context(tmp_path, monkeypatch):
    """Without delegation context (vars are None), record_backend_llm_call()
    returns silently — no crash, no trace written."""
    pytest.importorskip("aider")

    storage = _storage_for(tmp_path, monkeypatch)
    monkeypatch.setenv("MCP_CODER_OBS_VERBOSITY", "lean")
    delegation_id = "ctx-missing-silent"

    clear_delegation_context()

    from core.observability import get_observability

    get_observability().record_backend_llm_call(
        call_type="executor_turn",
        model="test/model",
        usage=None,
        duration_ms=10,
    )

    trace_path = storage.session_dir / "traces" / f"{delegation_id}.jsonl"
    assert not trace_path.exists(), (
        "No trace should be written when delegation context vars are missing"
    )


# ── AiderEngine integration: pool.submit receives ctx.run ───────────────────


def test_aider_engine_submits_with_ctx_run(monkeypatch):
    """Verify that AiderEngine._execute_delegation uses pool.submit(ctx.run, fn)
    rather than pool.submit(fn) directly — i.e., the context propagation fix
    is wired into the engine's threadpool path."""
    pytest.importorskip("aider")
    from core.engine.aider_engine import AiderEngine

    submit_calls: list[tuple] = []

    class _CapturingFuture:
        def result(self, timeout=None):
            return (MagicMock(), MagicMock(), "ok", "", False, False)

        def cancel(self):
            pass

    class _CapturingPool:
        def submit(self, fn, *args, **kwargs):
            submit_calls.append((fn, args, kwargs))
            return _CapturingFuture()

        def shutdown(self, wait=True, cancel_futures=False):
            pass

    engine = AiderEngine("test/model")

    with (
        patch("core.engine.aider_engine.os.chdir"),
        patch("core.engine.aider_engine.begin_delegation_snapshot", return_value=None),
        patch("core.engine.aider_engine.snapshot_git_dirty", return_value=set()),
        patch("core.engine.aider_engine.snapshot_mtimes", return_value={}),
        patch(
            "core.engine.aider_engine.resolve_delegation_attribution",
            return_value=([], [], {}, False, 0),
        ),
        patch(
            "core.engine.aider_engine.concurrent.futures.ThreadPoolExecutor",
            return_value=_CapturingPool(),
        ),
        patch("core.engine.observable_model.ObservableModel"),
    ):
        engine._execute_delegation(
            prompt="do thing",
            fnames_rel=["a.py"],
            edit_paths_rel=["a.py"],
            workspace_path="/tmp/ws",
            mcp_session_id=None,
            delegation_id="eng-ctx-test",
        )

    assert len(submit_calls) == 1, "Expected exactly one pool.submit() call"
    submitted_fn, submitted_args, _ = submit_calls[0]

    # The first argument must be a Context.run bound method, not _run_coder directly
    assert callable(submitted_fn), "First arg to submit must be callable"
    # Context.run is a builtin_function_or_method named 'run'; its __self__ is a Context
    ctx_obj = getattr(submitted_fn, "__self__", None)
    assert ctx_obj is not None, (
        "pool.submit() first arg should be ctx.run (a bound method of a Context)"
    )
    assert type(ctx_obj).__name__ == "Context", (
        f"Expected a contextvars.Context, got {type(ctx_obj)}"
    )
    # The wrapped function (_run_coder) is the first positional arg
    assert len(submitted_args) == 1 and callable(submitted_args[0]), (
        "_run_coder should be passed as positional arg to ctx.run"
    )

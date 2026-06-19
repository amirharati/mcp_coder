from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from unittest.mock import patch

import main
import pytest

from core.cli.logs_tail import (
    _format_human_event,
    read_appended_events,
    resolve_latest_trace,
    resolve_trace_for_delegation,
    tail_trace_file,
)
from core.engine.base import ExecutionResult
from core.storage.paths import session_folder
from server.mcp_server import delegate_to_agent


class _FakeCtx:
    def __init__(self) -> None:
        self.messages: list[str] = []

    async def info(self, message: str) -> None:
        self.messages.append(message)


class _FailingCtx:
    async def info(self, _message: str) -> None:
        raise RuntimeError("notification failed")


def _seed_workspace(tmp_path: Path, monkeypatch) -> Path:
    home = tmp_path / "home"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("MCP_CODER_HOME", str(home))
    monkeypatch.setenv("MCP_CODER_USE_CONTEXT_PACKAGE", "0")
    monkeypatch.chdir(workspace)
    monkeypatch.delenv("MCP_CODER_LOG_DIR", raising=False)
    return workspace


def _mock_engine_with_result(result: ExecutionResult):
    return type(
        "MockEngine",
        (),
        {
            "model_name": "openrouter/openai/gpt-4o-mini",
            "backend_id": "aider",
            "run": lambda *a, **k: result,
        },
    )()


def test_delegate_notifications_emit_milestones(tmp_path, monkeypatch):
    _seed_workspace(tmp_path, monkeypatch)
    ctx = _FakeCtx()
    result = ExecutionResult(
        success=True,
        output="done",
        files_changed=["hello.py"],
        model="openrouter/openai/gpt-4o-mini",
        tokens={"source": "unavailable"},
    )

    with patch("server.mcp_server.get_engine", return_value=_mock_engine_with_result(result)):
        raw = delegate_to_agent(
            task="Add hello world",
            target_files=["hello.py"],
            context_summary="Python project",
            backend="aider",
            ctx=ctx,
        )

    payload = json.loads(raw)
    assert payload["success"] is True
    joined = "\n".join(ctx.messages)
    assert "[compile] Starting context compilation" in joined
    assert "[compile] Context ready" in joined
    assert "[validation] Spec validation" in joined
    assert "[executor] Starting delegated run" in joined
    assert "[done] Delegation complete — success." in joined


def test_delegate_notifications_are_non_fatal_on_ctx_error(tmp_path, monkeypatch):
    _seed_workspace(tmp_path, monkeypatch)
    result = ExecutionResult(
        success=True,
        output="ok",
        files_changed=[],
        model="openrouter/openai/gpt-4o-mini",
        tokens={"source": "unavailable"},
    )
    with patch("server.mcp_server.get_engine", return_value=_mock_engine_with_result(result)):
        raw = delegate_to_agent(
            task="No-op",
            target_files=["hello.py"],
            context_summary="ctx",
            backend="aider",
            ctx=_FailingCtx(),
        )
    payload = json.loads(raw)
    assert payload["success"] is True


def _write_trace_session(
    workspace: Path,
    *,
    session_id: str,
    delegation_id: str,
    timestamp_end: str,
    events: list[dict] | None = None,
) -> Path:
    session_dir = session_folder(workspace, session_id)
    traces = session_dir / "traces"
    traces.mkdir(parents=True, exist_ok=True)
    trace_path = traces / f"{delegation_id}.jsonl"
    if events is not None:
        trace_path.write_text(
            "\n".join(json.dumps(event, ensure_ascii=False) for event in events) + "\n",
            encoding="utf-8",
        )
    row = {
        "delegation_id": delegation_id,
        "timestamp_end": timestamp_end,
        "session_dir": str(session_dir.resolve()),
        "trace_ref": f"traces/{delegation_id}.jsonl",
    }
    (session_dir / "delegations.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
    return trace_path


def test_logs_tail_resolve_latest_and_specific(tmp_path, monkeypatch):
    workspace = _seed_workspace(tmp_path, monkeypatch)
    path_old = _write_trace_session(
        workspace,
        session_id="sess-old",
        delegation_id="deleg-old",
        timestamp_end="2026-06-18T20:00:00Z",
        events=[],
    )
    path_new = _write_trace_session(
        workspace,
        session_id="sess-new",
        delegation_id="deleg-new",
        timestamp_end="2026-06-18T21:00:00Z",
        events=[],
    )
    latest_id, latest_path = resolve_latest_trace(workspace)
    assert latest_id == "deleg-new"
    assert latest_path == path_new
    assert resolve_trace_for_delegation(workspace, "deleg-old") == path_old


def test_logs_tail_read_appended_events_missing_file(tmp_path, monkeypatch):
    workspace = _seed_workspace(tmp_path, monkeypatch)
    missing_path = workspace / "does-not-exist.jsonl"
    events, offset, exists = read_appended_events(missing_path, offset=0)
    assert events == []
    assert offset == 0
    assert exists is False


def test_logs_tail_human_and_json_formatters(tmp_path, monkeypatch):
    workspace = _seed_workspace(tmp_path, monkeypatch)
    events = [
        {"type": "trace_header", "timestamp": "2026-06-18T20:00:00Z", "delegation_id": "d1"},
        {"type": "compile_event", "timestamp": "2026-06-18T20:00:01Z", "stage": "builder"},
        {"type": "executor_step", "timestamp": "2026-06-18T20:00:02Z", "step_index": 1, "status": "ok"},
        {"type": "llm_call", "timestamp": "2026-06-18T20:00:03Z", "role": "executor", "model": "x"},
        {"type": "proxy_llm_call", "timestamp": "2026-06-18T20:00:04Z", "call_index": 2, "status_code": 200},
        {"type": "backend_llm_call", "timestamp": "2026-06-18T20:00:05Z", "call_index": 2, "model": "x"},
        {"type": "delegation_complete", "timestamp": "2026-06-18T20:00:06Z", "success": True, "outcome": "success"},
    ]
    trace_path = _write_trace_session(
        workspace,
        session_id="sess-tail",
        delegation_id="deleg-tail",
        timestamp_end="2026-06-18T20:00:06Z",
        events=events,
    )

    out_human = io.StringIO()
    rc_human = tail_trace_file(trace_path, output_format="human", follow=False, stdout=out_human)
    assert rc_human == 0
    text = out_human.getvalue()
    assert "trace_header" in text
    assert "compile_event" in text
    assert "executor_step" in text
    assert "llm_call" in text
    assert "proxy_llm_call" in text
    assert "backend_llm_call" in text
    assert "delegation_complete" in text

    out_json = io.StringIO()
    rc_json = tail_trace_file(trace_path, output_format="json", follow=False, stdout=out_json)
    assert rc_json == 0
    parsed = [json.loads(line) for line in out_json.getvalue().splitlines() if line.strip()]
    assert [row["type"] for row in parsed] == [event["type"] for event in events]


def test_format_human_event_handles_required_types():
    required_types = [
        "trace_header",
        "compile_event",
        "executor_step",
        "llm_call",
        "proxy_llm_call",
        "backend_llm_call",
        "delegation_complete",
    ]
    for event_type in required_types:
        rendered = _format_human_event({"type": event_type, "timestamp": "2026-06-18T00:00:00Z"})
        assert event_type in rendered


def test_main_dispatch_logs_tail(monkeypatch):
    with patch("core.cli.logs_tail.main_logs_tail", return_value=0) as tail_mock:
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "mcp-coder",
                "logs",
                "tail",
                "--latest",
                "--format",
                "json",
            ],
        )
        with pytest.raises(SystemExit) as exc:
            main.main()
    assert exc.value.code == 0
    tail_mock.assert_called_once_with(["--latest", "--format", "json"])

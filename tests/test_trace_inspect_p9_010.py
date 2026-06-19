"""Tests for trace inspect CLI (P9-010)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import main

from core.cli.trace_inspect import main_trace_inspect
from core.storage.paths import session_folder


def _seed_workspace(
    tmp_path: Path,
    monkeypatch,
    *,
    delegation_id: str = "trace-inspect-1",
) -> tuple[Path, str]:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    home = tmp_path / "home"
    monkeypatch.setenv("MCP_CODER_HOME", str(home))

    session_dir = session_folder(workspace, "sess-1")
    traces = session_dir / "traces"
    traces.mkdir(parents=True)
    events = [
        {"type": "trace_header", "timestamp": "2026-06-15T19:00:00Z", "delegation_id": delegation_id},
        {"type": "compile_event", "timestamp": "2026-06-15T19:00:01Z", "compile_type": "compile", "files_count": 3},
        {
            "type": "proxy_llm_call",
            "timestamp": "2026-06-15T19:00:03Z",
            "call_index": 1,
            "step_index": 1,
            "status_code": 200,
            "wire_latency_ms": 1993,
            "raw_request": "X" * 2205,
            "raw_response": '{"ok":true}',
        },
        {
            "type": "backend_llm_call",
            "timestamp": "2026-06-15T19:00:05Z",
            "call_index": 1,
            "step_index": 1,
            "model": "openrouter/test",
            "usage": {"input": 10, "output": 2, "total": 12},
            "response_body": "backend-body",
        },
    ]
    (traces / f"{delegation_id}.jsonl").write_text(
        "\n".join(json.dumps(event) for event in events) + "\n",
        encoding="utf-8",
    )

    row = {
        "delegation_id": delegation_id,
        "timestamp_end": "2026-06-15T19:00:06Z",
        "session_dir": str(session_dir.resolve()),
        "trace_ref": f"traces/{delegation_id}.jsonl",
    }
    (session_dir / "delegations.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
    return workspace, delegation_id


def test_inspect_lists_all_events(tmp_path, monkeypatch, capsys):
    workspace, delegation_id = _seed_workspace(tmp_path, monkeypatch)
    rc = main_trace_inspect([delegation_id, "--workspace", str(workspace)])
    assert rc == 0
    out = capsys.readouterr().out
    assert f"Trace: {delegation_id}" in out
    assert "trace_header" in out
    assert "compile_event" in out
    assert "proxy_llm_call" in out
    assert "backend_llm_call" in out


def test_inspect_filter_by_type(tmp_path, monkeypatch, capsys):
    workspace, delegation_id = _seed_workspace(tmp_path, monkeypatch)
    rc = main_trace_inspect(
        [delegation_id, "--workspace", str(workspace), "--type", "proxy_llm_call"]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "proxy_llm_call" in out
    assert "backend_llm_call" not in out


def test_inspect_select_event_n(tmp_path, monkeypatch, capsys):
    workspace, delegation_id = _seed_workspace(tmp_path, monkeypatch)
    rc = main_trace_inspect(
        [delegation_id, "--workspace", str(workspace), "--type", "proxy_llm_call", "--event", "1"]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert out.count("proxy_llm_call") == 1


def test_inspect_event_out_of_range(tmp_path, monkeypatch, capsys):
    workspace, delegation_id = _seed_workspace(tmp_path, monkeypatch)
    rc = main_trace_inspect(
        [delegation_id, "--workspace", str(workspace), "--type", "proxy_llm_call", "--event", "99"]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "out of range" in out


def test_inspect_field_human(tmp_path, monkeypatch, capsys):
    workspace, delegation_id = _seed_workspace(tmp_path, monkeypatch)
    rc = main_trace_inspect(
        [
            delegation_id,
            "--workspace",
            str(workspace),
            "--type",
            "proxy_llm_call",
            "--field",
            "raw_request",
            "--format",
            "human",
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "--- raw_request ---" in out
    assert "[TRUNCATED" in out


def test_inspect_field_json(tmp_path, monkeypatch, capsys):
    workspace, delegation_id = _seed_workspace(tmp_path, monkeypatch)
    rc = main_trace_inspect(
        [
            delegation_id,
            "--workspace",
            str(workspace),
            "--type",
            "proxy_llm_call",
            "--field",
            "raw_request",
            "--format",
            "json",
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    value = json.loads(out)
    assert isinstance(value, str)
    assert len(value) == 2205


def test_inspect_field_missing(tmp_path, monkeypatch, capsys):
    workspace, delegation_id = _seed_workspace(tmp_path, monkeypatch)
    rc = main_trace_inspect(
        [delegation_id, "--workspace", str(workspace), "--field", "nonexistent_field"]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "(null)" in out


def test_inspect_unknown_id(tmp_path, monkeypatch, capsys):
    workspace, _delegation_id = _seed_workspace(tmp_path, monkeypatch)
    rc = main_trace_inspect(["missing-id", "--workspace", str(workspace)])
    assert rc == 1
    out = capsys.readouterr().out
    assert "delegation not found: missing-id" in out


def test_inspect_json_full_event(tmp_path, monkeypatch, capsys):
    workspace, delegation_id = _seed_workspace(tmp_path, monkeypatch)
    rc = main_trace_inspect(
        [
            delegation_id,
            "--workspace",
            str(workspace),
            "--type",
            "backend_llm_call",
            "--event",
            "1",
            "--format",
            "json",
        ]
    )
    assert rc == 0
    event = json.loads(capsys.readouterr().out)
    assert event["type"] == "backend_llm_call"
    assert event["response_body"] == "backend-body"


def test_main_dispatch_trace_inspect(monkeypatch):
    with patch("core.cli.trace_inspect.main_trace_inspect", return_value=0) as inspect_mock:
        monkeypatch.setattr(
            sys,
            "argv",
            ["mcp-coder", "trace", "inspect", "deleg-1", "--format", "json"],
        )
        try:
            main.main()
        except SystemExit as exc:
            assert exc.code == 0
    inspect_mock.assert_called_once_with(["trace", "inspect", "deleg-1", "--format", "json"])


def test_inspect_summary_human(tmp_path, monkeypatch, capsys):
    workspace, delegation_id = _seed_workspace(tmp_path, monkeypatch)
    rc = main_trace_inspect([delegation_id, "--workspace", str(workspace), "--summary"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Trace summary" in out
    assert "event_counts_by_type" in out
    assert "policy_applied_coverage" in out
    assert "proxy_alignment" in out


def test_inspect_summary_json(tmp_path, monkeypatch, capsys):
    workspace, delegation_id = _seed_workspace(tmp_path, monkeypatch)
    rc = main_trace_inspect(
        [delegation_id, "--workspace", str(workspace), "--summary", "--format", "json"]
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert "event_counts_by_type" in payload
    assert "token_totals" in payload
    assert "policy_applied_coverage" in payload
    assert "proxy_alignment" in payload

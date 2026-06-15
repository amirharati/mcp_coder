"""Tests for replay CLI (P9-004)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import main
import pytest
from core.cli.replay import main_replay
from core.storage.paths import session_folder


def _seed_workspace(
    tmp_path: Path,
    monkeypatch,
    *,
    include_blob: bool = True,
    include_trace: bool = True,
) -> tuple[Path, str]:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    home = tmp_path / "home"
    monkeypatch.setenv("MCP_CODER_HOME", str(home))

    delegation_id = "deleg-123"
    session_id = "sess-1"
    session_dir = session_folder(workspace, session_id)
    traces_dir = session_dir / "traces"
    context_dir = session_dir / "context_packages"
    traces_dir.mkdir(parents=True)
    context_dir.mkdir(parents=True)

    row = {
        "type": "delegation",
        "delegation_id": delegation_id,
        "timestamp_start": "2026-06-15T10:00:00Z",
        "timestamp_end": "2026-06-15T10:00:02Z",
        "duration_ms": 2000,
        "backend": "aider",
        "success": True,
        "delegate_mode": "edit",
        "mcp_request": {
            "task": "Update replay command",
            "target_files": ["core/cli/replay.py"],
        },
        "spec_path": "docs/tasks/P9-004-replay-cli-v1.md",
        "files_changed": ["core/cli/replay.py", "main.py"],
        "files_unexpected": [],
        "checkpoint": {"status": "ok"},
        "outcome": "success",
        "session_dir": str(session_dir.resolve()),
        "trace_ref": f"traces/{delegation_id}.jsonl",
        "context": {"context_package_hash": "ctx-hash-1"},
    }
    (session_dir / "delegations.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")

    if include_trace:
        trace_lines = [
            {"type": "trace_header", "delegation_id": delegation_id},
            {"type": "proxy_llm_call", "model": "proxy-model", "call_index": 1, "latency_ms": 21},
            {
                "type": "backend_llm_call",
                "model": "backend-model",
                "call_index": 2,
                "duration_ms": 31,
            },
        ]
        (traces_dir / f"{delegation_id}.jsonl").write_text(
            "\n".join(json.dumps(item) for item in trace_lines) + "\n",
            encoding="utf-8",
        )

    if include_blob:
        blob = {
            "entries": [{"path": "core/cli/replay.py"}],
            "metadata": {"delegate_mode": "edit"},
            "policies": {"read_only": False},
        }
        (context_dir / "ctx-hash-1.json").write_text(json.dumps(blob), encoding="utf-8")

    return workspace, delegation_id


def test_replay_found_human_output(tmp_path, monkeypatch, capsys):
    workspace, delegation_id = _seed_workspace(tmp_path, monkeypatch)
    rc = main_replay([delegation_id, "--workspace", str(workspace)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Replay" in out
    assert f"- delegation_id: {delegation_id}" in out
    assert "Context Package" in out
    assert "- status: found" in out
    assert "Trace" in out
    assert "'proxy_llm_call': 1" in out
    assert "'backend_llm_call': 1" in out


def test_replay_found_json_output_shape(tmp_path, monkeypatch, capsys):
    workspace, delegation_id = _seed_workspace(tmp_path, monkeypatch)
    rc = main_replay([delegation_id, "--workspace", str(workspace), "--format", "json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["found"] is True
    assert payload["delegation"]["delegation_id"] == delegation_id
    assert payload["context_blob"]["status"] == "found"
    assert payload["context_blob"]["hash"] == "ctx-hash-1"
    assert payload["trace"]["status"] == "found"
    assert isinstance(payload["trace"]["events"], list)
    assert payload["trace"]["counts_by_type"]["trace_header"] == 1
    assert isinstance(payload["warnings"], list)


def test_replay_unknown_id_returns_1(tmp_path, monkeypatch, capsys):
    workspace, _ = _seed_workspace(tmp_path, monkeypatch)
    rc = main_replay(["unknown-id", "--workspace", str(workspace)])
    assert rc == 1
    err = capsys.readouterr().err
    assert "delegation not found: unknown-id" in err


def test_replay_missing_blob_warns_but_succeeds(tmp_path, monkeypatch, capsys):
    workspace, delegation_id = _seed_workspace(tmp_path, monkeypatch, include_blob=False)
    rc = main_replay([delegation_id, "--workspace", str(workspace)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Context Package" in out
    assert "- status: missing" in out
    assert "Warnings" in out
    assert "context blob missing" in out


def test_replay_missing_trace_warns_but_succeeds(tmp_path, monkeypatch, capsys):
    workspace, delegation_id = _seed_workspace(tmp_path, monkeypatch, include_trace=False)
    rc = main_replay([delegation_id, "--workspace", str(workspace)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Trace" in out
    assert "- status: missing" in out
    assert "Warnings" in out
    assert "trace missing for delegation" in out


def test_main_replay_subcommand_dispatch(monkeypatch):
    with patch("core.cli.replay.main_replay", return_value=0) as replay_mock:
        monkeypatch.setattr(
            sys,
            "argv",
            ["mcp-coder", "replay", "deleg-123", "--workspace", "/tmp/ws", "--format", "json"],
        )
        with pytest.raises(SystemExit) as exc:
            main.main()
    assert exc.value.code == 0
    replay_mock.assert_called_once_with(
        ["deleg-123", "--workspace", "/tmp/ws", "--format", "json"]
    )

"""Delegation diff query, MCP tool, and delegate response (P3-322d)."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from unittest.mock import patch

from core.engine.base import ExecutionResult
from core.workspace.history_query import (
    apply_diff_truncation,
    build_delegation_diff,
    delegation_diff_for_mcp,
    list_delegations,
)
from core.workspace.snapshot import begin_delegation_snapshot, resolve_delegation_attribution
from server.mcp_server import delegate_to_agent, get_delegation_diff


def _seed_delegation(ws, home, monkeypatch, *, delegation_id: str | None = None) -> str:
    monkeypatch.setenv("MCP_CODER_HOME", str(home))
    monkeypatch.delenv("MCP_CODER_DISABLE_WORKSPACE_SNAPSHOT", raising=False)
    did = delegation_id or str(uuid.uuid4())
    (ws / "foo.py").write_text("alpha\n", encoding="utf-8")
    session = begin_delegation_snapshot(
        workspace_path=str(ws),
        delegation_id=did,
        mcp_session_id="sess-dd",
        timestamp_start="2026-06-08T00:00:00Z",
        spec_path="tasks/foo.md",
        contract_paths=["foo.py"],
    )
    (ws / "foo.py").write_text("alpha\nbeta\n", encoding="utf-8")
    (ws / "new.py").write_text("fresh\n", encoding="utf-8")
    resolve_delegation_attribution(
        workspace_path=str(ws),
        snapshot_session=session,
        contract_paths=["foo.py"],
        edit_paths_rel=["foo.py"],
        before_git=None,
        before_mtimes=None,
        delegation_id=did,
    )
    return did


def test_build_delegation_diff_from_seeded_db(tmp_path, monkeypatch):
    home = tmp_path / "home"
    ws = tmp_path / "ws"
    ws.mkdir()
    did = _seed_delegation(ws, home, monkeypatch)

    diff = build_delegation_diff(ws, did)
    assert diff is not None
    assert diff.delegation_id == did
    assert "foo.py" in diff.modified
    assert "new.py" in diff.created
    assert "foo.py" in diff.diffs
    assert "@@" in diff.diffs["foo.py"]
    assert diff.spec_path == "tasks/foo.md"
    assert diff.timestamp_end is not None


def test_diff_truncation_env(monkeypatch):
    monkeypatch.setenv("MCP_CODER_DIFF_MAX_CHARS_PER_FILE", "50")
    monkeypatch.setenv("MCP_CODER_DIFF_MAX_TOTAL_CHARS", "80")
    big = "x" * 200
    diffs, truncated, paths = apply_diff_truncation({"a.py": big, "b.py": big})
    assert truncated is True
    assert paths
    assert sum(len(v) for v in diffs.values()) <= 80 + 50


def test_list_delegations(tmp_path, monkeypatch):
    home = tmp_path / "home"
    ws = tmp_path / "ws"
    ws.mkdir()
    did = _seed_delegation(ws, home, monkeypatch)

    rows = list_delegations(ws, limit=5)
    assert len(rows) == 1
    assert rows[0]["delegation_id"] == did
    assert rows[0]["modified_count"] == 1
    assert rows[0]["created_count"] == 1


def test_get_delegation_diff_tool_found(tmp_path, monkeypatch):
    home = tmp_path / "home"
    ws = tmp_path / "ws"
    ws.mkdir()
    did = _seed_delegation(ws, home, monkeypatch)
    monkeypatch.chdir(ws)

    raw = get_delegation_diff(did)
    payload = json.loads(raw)
    assert payload["found"] is True
    assert payload["delegation_diff"]["delegation_id"] == did
    assert "foo.py" in payload["delegation_diff"]["diffs"]


def test_get_delegation_diff_tool_not_found(tmp_path, monkeypatch):
    home = tmp_path / "home"
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setenv("MCP_CODER_HOME", str(home))
    monkeypatch.chdir(ws)

    raw = get_delegation_diff("00000000-0000-0000-0000-000000000000")
    payload = json.loads(raw)
    assert payload["found"] is False
    assert "error" in payload


def test_delegate_response_includes_delegation_diff(tmp_path, monkeypatch):
    home = tmp_path / "home"
    ws = tmp_path / "workspace"
    ws.mkdir()
    monkeypatch.setenv("MCP_CODER_HOME", str(home))
    monkeypatch.chdir(ws)

    fake_diff = {
        "delegation_id": "test-id",
        "created": ["new.py"],
        "modified": ["foo.py"],
        "deleted": [],
        "diffs": {"foo.py": "--- foo.py\n+++ foo.py\n"},
    }

    fake = ExecutionResult(
        success=True,
        output="done",
        files_changed=["foo.py", "new.py"],
        model="m",
        workspace_snapshot={"attribution_source": "manifest", "delta": {}},
    )
    mock_engine = type("E", (), {"model_name": "m", "run": lambda *a, **k: fake})()

    with patch("server.mcp_server.get_engine", return_value=mock_engine), patch(
        "core.workspace.history_query.safe_delegation_diff_dict",
        return_value=fake_diff,
    ):
        raw = delegate_to_agent(
            task="t",
            target_files=["foo.py"],
            context_summary="c",
            backend="aider",
        )

    payload = json.loads(raw)
    assert payload["delegation_diff"] == fake_diff


def test_delegate_response_omits_delegation_diff_when_snapshot_disabled(tmp_path, monkeypatch):
    home = tmp_path / "home"
    ws = tmp_path / "workspace"
    ws.mkdir()
    monkeypatch.setenv("MCP_CODER_HOME", str(home))
    monkeypatch.setenv("MCP_CODER_DISABLE_WORKSPACE_SNAPSHOT", "1")
    monkeypatch.chdir(ws)

    fake = ExecutionResult(
        success=True,
        output="done",
        files_changed=["foo.py"],
        model="m",
        workspace_snapshot=None,
    )
    mock_engine = type("E", (), {"model_name": "m", "run": lambda *a, **k: fake})()

    with patch("server.mcp_server.get_engine", return_value=mock_engine):
        raw = delegate_to_agent(
            task="t",
            target_files=["foo.py"],
            context_summary="c",
            backend="aider",
        )

    payload = json.loads(raw)
    assert "delegation_diff" not in payload


def test_delegation_diff_for_mcp_when_db_missing(tmp_path, monkeypatch):
    monkeypatch.delenv("MCP_CODER_DISABLE_WORKSPACE_SNAPSHOT", raising=False)
    result = delegation_diff_for_mcp(tmp_path, "missing-id")
    assert result["found"] is False

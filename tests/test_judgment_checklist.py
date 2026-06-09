"""Judgment checklist builder and implement delegate responses (P4-006)."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from core.engine.base import ExecutionResult
from core.host.cursor_rules import bundled_cursor_rules_dir
from core.workspace.judgment_checklist import build_judgment_checklist
from server.mcp_server import delegate_to_agent


def test_build_judgment_checklist_from_delegation_diff() -> None:
    diff = {
        "delegation_id": "abc-123",
        "created": ["new.py"],
        "modified": ["foo.py"],
        "deleted": ["old.py"],
        "diffs": {"foo.py": "--- a\n+++ b\n"},
    }
    checklist = build_judgment_checklist(
        delegation_diff=diff,
        files_unexpected=["extra.py"],
    )
    assert checklist["delegation_id"] == "abc-123"
    assert checklist["created"] == ["new.py"]
    assert checklist["modified"] == ["foo.py"]
    assert checklist["deleted"] == ["old.py"]
    assert checklist["files_unexpected"] == ["extra.py"]
    assert checklist["files_unexpected_warning"] is True
    assert "before pytest" in checklist["reminder"]
    assert "diffs" not in checklist


def test_build_judgment_checklist_no_unexpected_warning() -> None:
    checklist = build_judgment_checklist(
        delegation_diff={
            "delegation_id": "x",
            "created": [],
            "modified": ["a.py"],
            "deleted": [],
        },
        files_unexpected=[],
    )
    assert "files_unexpected_warning" not in checklist


def test_delegate_implement_includes_judgment_checklist(tmp_path, monkeypatch):
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
    assert "judgment_checklist" in payload
    checklist = payload["judgment_checklist"]
    assert checklist["delegation_id"] == "test-id"
    assert checklist["created"] == ["new.py"]
    assert checklist["modified"] == ["foo.py"]
    assert checklist["deleted"] == []
    assert "reminder" in checklist
    assert payload["delegation_diff"] == fake_diff


def test_delegate_review_omits_judgment_checklist(tmp_path, monkeypatch):
    home = tmp_path / "home"
    ws = tmp_path / "workspace"
    ws.mkdir()
    monkeypatch.setenv("MCP_CODER_HOME", str(home))
    monkeypatch.chdir(ws)

    fake = ExecutionResult(
        success=True,
        output="questions",
        files_changed=[],
        model="m",
        workspace_snapshot={"attribution_source": "manifest", "delta": {}},
    )
    mock_engine = type("E", (), {"model_name": "m", "run": lambda *a, **k: fake})()

    with patch("server.mcp_server.get_engine", return_value=mock_engine), patch(
        "core.workspace.history_query.safe_delegation_diff_dict",
        return_value={"delegation_id": "x", "created": [], "modified": [], "deleted": []},
    ) as mock_diff:
        raw = delegate_to_agent(
            task="t",
            target_files=[],
            context_summary="c",
            backend="aider",
            mode="review",
        )

    payload = json.loads(raw)
    assert "judgment_checklist" not in payload
    mock_diff.assert_not_called()


def test_delegate_omits_judgment_checklist_when_snapshot_disabled(tmp_path, monkeypatch):
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
    assert "judgment_checklist" not in payload
    assert "delegation_diff" not in payload


def test_bundled_rules_judgment_loop_versions() -> None:
    rules_dir = bundled_cursor_rules_dir()
    for path in (
        rules_dir / "use-mcp-coder.default.mdc",
        rules_dir / "use-mcp-coder.strict.mdc",
    ):
        text = path.read_text(encoding="utf-8")
        assert 'mcp_coder_rule_version: "12"' in text
        assert "judgment_checklist" in text
        assert "reading source files" in text.lower() or "reading source" in text.lower()

    history = (rules_dir / "workspace-history.mdc").read_text(encoding="utf-8")
    assert 'mcp_coder_rule_version: "6"' in history
    assert "Order of operations" in history
    assert "Forbidden shortcuts" in history
    assert "Delegation judgment" in history
    assert "Read" in history and "for verify" in history

"""Builder history gather (P4-001b)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import core.context.builder_history as bh
from core.context.builder_history import (
    BuilderHistoryContext,
    gather_builder_history,
)


def test_empty_when_snapshot_disabled(tmp_path, monkeypatch):
    monkeypatch.setattr(bh, "is_snapshot_enabled", lambda: False)
    result = gather_builder_history(tmp_path, spec_path="tasks/widget.md")
    assert result.is_empty()
    assert result.same_spec == []
    assert result.project_recent == []


def test_empty_when_list_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(bh, "is_snapshot_enabled", lambda: True)

    def _boom(*a, **k):
        raise RuntimeError("db gone")

    monkeypatch.setattr(bh, "list_delegations", _boom)
    result = gather_builder_history(tmp_path, spec_path="tasks/widget.md")
    assert result.is_empty()


def _row(did: str, spec: str | None) -> dict[str, Any]:
    return {
        "delegation_id": did,
        "spec_path": spec,
        "outcome": "applied",
        "checkpoint_summary": f"summary {did}",
        "created_count": 1,
        "modified_count": 2,
        "deleted_count": 0,
        "delegate_mode": "implement",
        "timestamp_end": "2026-06-09T00:00:00Z",
        "model": "m",
    }


def test_filters_same_spec_vs_project(tmp_path, monkeypatch):
    monkeypatch.setattr(bh, "is_snapshot_enabled", lambda: True)

    same = [_row("a1", "tasks/widget.md"), _row("a2", "tasks/widget.md")]
    project = [
        _row("a1", "tasks/widget.md"),  # dup — must be filtered from project
        _row("b1", "tasks/other.md"),
        _row("b2", None),
    ]

    def _fake_list(workspace, *, limit, spec_path=None, file_path=None):
        if spec_path:
            return same[:limit]
        return project[:limit]

    monkeypatch.setattr(bh, "list_delegations", _fake_list)

    result = gather_builder_history(tmp_path, spec_path="tasks/widget.md")
    same_ids = [r["delegation_id"] for r in result.same_spec]
    project_ids = [r["delegation_id"] for r in result.project_recent]
    assert same_ids == ["a1", "a2"]
    assert "a1" not in project_ids
    assert project_ids == ["b1", "b2"]
    # summary-only fields
    assert set(result.same_spec[0]) == {
        "delegation_id",
        "outcome",
        "checkpoint_summary",
        "created_count",
        "modified_count",
        "delegate_mode",
        "timestamp_end",
    }


def test_respects_env_limits(tmp_path, monkeypatch):
    monkeypatch.setattr(bh, "is_snapshot_enabled", lambda: True)
    monkeypatch.setenv("MCP_CODER_BUILDER_HISTORY_SPEC_LIMIT", "1")
    monkeypatch.setenv("MCP_CODER_BUILDER_HISTORY_PROJECT_LIMIT", "1")

    captured: dict[str, Any] = {}

    def _fake_list(workspace, *, limit, spec_path=None, file_path=None):
        if spec_path:
            captured["spec_limit"] = limit
            return [_row("a1", "tasks/widget.md")]
        captured["project_limit"] = limit
        return [_row("b1", "tasks/other.md"), _row("b2", None)]

    monkeypatch.setattr(bh, "list_delegations", _fake_list)
    result = gather_builder_history(tmp_path, spec_path="tasks/widget.md")
    assert captured["spec_limit"] == 1
    assert len(result.same_spec) == 1
    assert len(result.project_recent) == 1


def test_no_spec_path_only_project(tmp_path, monkeypatch):
    monkeypatch.setattr(bh, "is_snapshot_enabled", lambda: True)

    def _fake_list(workspace, *, limit, spec_path=None, file_path=None):
        assert spec_path is None
        return [_row("b1", None)]

    monkeypatch.setattr(bh, "list_delegations", _fake_list)
    result = gather_builder_history(tmp_path, spec_path=None)
    assert result.same_spec == []
    assert [r["delegation_id"] for r in result.project_recent] == ["b1"]

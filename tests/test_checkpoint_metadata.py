"""Checkpoint metadata on snapshots rows (P3-322e)."""

from __future__ import annotations

import sqlite3
import subprocess
import sys
import uuid
from pathlib import Path

from core.workspace.checkpoint_summary import resolve_checkpoint_summary
from core.workspace.history_db import WorkspaceHistoryDB
from core.workspace.history_query import build_delegation_diff, list_delegations
from core.workspace.snapshot import begin_delegation_snapshot, resolve_delegation_attribution


def _write_spec(ws: Path, rel: str, body: str) -> None:
    path = ws / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def _seed_with_finalize(
    ws: Path,
    home: Path,
    monkeypatch,
    *,
    spec_body: str | None = None,
    task: str = "fallback task line",
) -> str:
    monkeypatch.setenv("MCP_CODER_HOME", str(home))
    monkeypatch.delenv("MCP_CODER_DISABLE_WORKSPACE_SNAPSHOT", raising=False)
    spec_rel = "tasks/checkpoint.md"
    if spec_body is not None:
        _write_spec(ws, f".mcp-coder/specs/{spec_rel}", spec_body)

    did = str(uuid.uuid4())
    (ws / "m.py").write_text("v1\n", encoding="utf-8")
    session = begin_delegation_snapshot(
        workspace_path=str(ws),
        delegation_id=did,
        mcp_session_id="sess-cp",
        timestamp_start="2026-06-08T00:00:00Z",
        spec_path=spec_rel if spec_body is not None else None,
        contract_paths=["m.py"],
    )
    (ws / "m.py").write_text("v1\nv2\n", encoding="utf-8")
    resolve_delegation_attribution(
        workspace_path=str(ws),
        snapshot_session=session,
        contract_paths=["m.py"],
        edit_paths_rel=["m.py"],
        before_git=None,
        before_mtimes=None,
        delegation_id=did,
    )

    summary = resolve_checkpoint_summary(
        task=task,
        spec_path=spec_rel if spec_body is not None else None,
        workspace=ws,
    )
    db = WorkspaceHistoryDB(ws)
    db.finalize_checkpoint_metadata(
        delegation_id=did,
        checkpoint_summary=summary,
        delegate_mode="implement",
        outcome="delegated_ok",
        model="test-model",
        duration_ms=42,
        tokens_total=100,
        error_class=None,
        delta_created=0,
        delta_modified=1,
        delta_deleted=0,
    )
    return did


def test_summary_from_spec_goal(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    _write_spec(
        ws,
        ".mcp-coder/specs/tasks/foo.md",
        "---\nspec_id: foo\n---\n\n## Goal\n\n- Implement CLI entrypoint\n",
    )
    summary = resolve_checkpoint_summary(
        task="ignored task",
        spec_path="tasks/foo.md",
        workspace=ws,
    )
    assert summary == "Implement CLI entrypoint"


def test_summary_from_task_only(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    summary = resolve_checkpoint_summary(
        task="Do the thing\nsecond line",
        spec_path=None,
        workspace=ws,
    )
    assert summary == "Do the thing"


def test_summary_truncation(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    long_line = "x" * 250
    summary = resolve_checkpoint_summary(
        task=long_line,
        spec_path=None,
        workspace=ws,
        max_chars=200,
    )
    assert len(summary) == 200
    assert summary.endswith("…")


def test_migration_adds_checkpoint_columns(tmp_path, monkeypatch):
    home = tmp_path / "home"
    ws = tmp_path / "ws"
    ws.mkdir()
    did = _seed_with_finalize(
        ws,
        home,
        monkeypatch,
        spec_body="---\nspec_id: m\n---\n\n## Goal\n\nMigrate columns\n",
    )
    db_path = WorkspaceHistoryDB(ws).db_path
    conn = sqlite3.connect(str(db_path))
    cols = {row[1] for row in conn.execute("PRAGMA table_info(snapshots)")}
    conn.close()
    assert "checkpoint_summary" in cols
    assert "delta_modified" in cols

    snap = WorkspaceHistoryDB(ws).get_snapshot(did)
    assert snap is not None
    assert snap["checkpoint_summary"] == "Migrate columns"
    assert snap["delta_modified"] == 1


def test_finalize_and_list_delegations(tmp_path, monkeypatch):
    home = tmp_path / "home"
    ws = tmp_path / "ws"
    ws.mkdir()
    did = _seed_with_finalize(
        ws,
        home,
        monkeypatch,
        spec_body="---\nspec_id: l\n---\n\n## Goal\n\nList me\n",
    )
    rows = list_delegations(ws, limit=5)
    assert len(rows) == 1
    row = rows[0]
    assert row["delegation_id"] == did
    assert row["checkpoint_summary"] == "List me"
    assert row["outcome"] == "delegated_ok"
    assert row["modified_count"] == 1

    diff = build_delegation_diff(ws, did)
    assert diff is not None
    assert diff.checkpoint_summary == "List me"


def test_history_list_cli_shows_summary(tmp_path, monkeypatch):
    home = tmp_path / "home"
    ws = tmp_path / "ws"
    ws.mkdir()
    _seed_with_finalize(
        ws,
        home,
        monkeypatch,
        spec_body="---\nspec_id: cli\n---\n\n## Goal\n\nCLI summary label\n",
    )
    repo = Path(__file__).resolve().parents[1]
    proc = subprocess.run(
        [sys.executable, "main.py", "history", "list", "--workspace", str(ws)],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert "CLI summary label" in proc.stdout

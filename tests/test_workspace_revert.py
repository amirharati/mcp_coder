"""Content snapshots, unified diffs, and revert (P3-322b)."""

from __future__ import annotations

import sqlite3
import uuid

import pytest

from core.storage.paths import workspace_history_db_path
from core.workspace.history_db import WorkspaceHistoryDB
from core.workspace.revert import revert_to_before
from core.workspace.snapshot import begin_delegation_snapshot, resolve_delegation_attribution
from core.workspace.walk import sha256_bytes


def _run_delegation(
    ws,
    home,
    monkeypatch,
    *,
    delegation_id: str,
    contract_paths: list[str],
    mutate,
) -> str:
    monkeypatch.setenv("MCP_CODER_HOME", str(home))
    monkeypatch.delenv("MCP_CODER_DISABLE_WORKSPACE_SNAPSHOT", raising=False)

    session = begin_delegation_snapshot(
        workspace_path=str(ws),
        delegation_id=delegation_id,
        mcp_session_id="sess-1",
        timestamp_start="2026-06-08T00:00:00Z",
        spec_path="tasks/foo.md",
        contract_paths=contract_paths,
    )
    mutate(ws)
    resolve_delegation_attribution(
        workspace_path=str(ws),
        snapshot_session=session,
        contract_paths=contract_paths,
        edit_paths_rel=contract_paths,
        before_git=None,
        before_mtimes=None,
        delegation_id=delegation_id,
    )
    return delegation_id


def test_modified_text_file_stores_unified_diff(tmp_path, monkeypatch):
    home = tmp_path / "home"
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "foo.py").write_text("alpha\n", encoding="utf-8")
    delegation_id = str(uuid.uuid4())

    _run_delegation(
        ws,
        home,
        monkeypatch,
        delegation_id=delegation_id,
        contract_paths=["foo.py"],
        mutate=lambda w: (w / "foo.py").write_text("alpha\nbeta\n", encoding="utf-8"),
    )

    db = WorkspaceHistoryDB(ws)
    rows = db.get_file_deltas(delegation_id)
    assert len(rows) == 1
    row = rows[0]
    assert row["change_type"] == "modified"
    assert row["diff"] is not None
    assert "@@" in str(row["diff"])
    assert "beta" in str(row["diff"])

    before_hash = sha256_bytes(b"alpha\n")
    after_hash = sha256_bytes(b"alpha\nbeta\n")
    assert db.fetch_blob(before_hash) == b"alpha\n"
    assert db.fetch_blob(after_hash) == b"alpha\nbeta\n"


def test_created_text_file_stores_blob_no_diff(tmp_path, monkeypatch):
    home = tmp_path / "home"
    ws = tmp_path / "ws"
    ws.mkdir()
    delegation_id = str(uuid.uuid4())

    _run_delegation(
        ws,
        home,
        monkeypatch,
        delegation_id=delegation_id,
        contract_paths=["new.py"],
        mutate=lambda w: (w / "new.py").write_text("fresh\n", encoding="utf-8"),
    )

    db = WorkspaceHistoryDB(ws)
    rows = db.get_file_deltas(delegation_id)
    assert rows[0]["change_type"] == "created"
    assert rows[0]["diff"] is None
    assert db.fetch_blob(str(rows[0]["content_hash"])) == b"fresh\n"


def test_binary_modified_has_no_diff(tmp_path, monkeypatch):
    home = tmp_path / "home"
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "data.bin").write_bytes(b"\xff\xfe\xfd")
    delegation_id = str(uuid.uuid4())

    _run_delegation(
        ws,
        home,
        monkeypatch,
        delegation_id=delegation_id,
        contract_paths=["data.bin"],
        mutate=lambda w: (w / "data.bin").write_bytes(b"\xff\xfe\xfc"),
    )

    db = WorkspaceHistoryDB(ws)
    rows = db.get_file_deltas(delegation_id)
    assert rows[0]["change_type"] == "modified"
    assert rows[0]["is_binary"] == 1
    assert rows[0]["diff"] is None
    assert rows[0]["prev_hash"] is not None
    assert rows[0]["content_hash"] is not None


def test_contract_snapshot_before_delta(tmp_path, monkeypatch):
    """Contract path content in blobs even when file unchanged during delegation."""
    home = tmp_path / "home"
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "edit.py").write_text("stable\n", encoding="utf-8")
    (ws / "read.py").write_text("context\n", encoding="utf-8")
    delegation_id = str(uuid.uuid4())

    session = begin_delegation_snapshot(
        workspace_path=str(ws),
        delegation_id=delegation_id,
        mcp_session_id="sess-1",
        timestamp_start="2026-06-08T00:00:00Z",
        spec_path="tasks/foo.md",
        contract_paths=["edit.py", "read.py"],
    )
    assert session is not None
    assert session.contract_paths_snapshotted == 2

    (ws / "extra.py").write_text("new\n", encoding="utf-8")
    _, _, meta, _, _ = resolve_delegation_attribution(
        workspace_path=str(ws),
        snapshot_session=session,
        contract_paths=["edit.py", "read.py"],
        edit_paths_rel=["edit.py"],
        before_git=None,
        before_mtimes=None,
        delegation_id=delegation_id,
    )
    assert meta is not None
    assert meta["contract_paths_snapshotted"] == 2
    assert meta["delta"]["created"] == ["extra.py"]

    db = WorkspaceHistoryDB(ws)
    assert db.fetch_blob(sha256_bytes(b"stable\n")) == b"stable\n"
    assert db.fetch_blob(sha256_bytes(b"context\n")) == b"context\n"


def test_revert_modified_restores_pre_delegation_content(tmp_path, monkeypatch):
    home = tmp_path / "home"
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "m.py").write_text("before\n", encoding="utf-8")
    delegation_id = str(uuid.uuid4())

    _run_delegation(
        ws,
        home,
        monkeypatch,
        delegation_id=delegation_id,
        contract_paths=["m.py"],
        mutate=lambda w: (w / "m.py").write_text("after\n", encoding="utf-8"),
    )
    assert (ws / "m.py").read_text(encoding="utf-8") == "after\n"

    reverted = revert_to_before(ws, delegation_id, ["m.py"])
    assert reverted == ["m.py"]
    assert (ws / "m.py").read_text(encoding="utf-8") == "before\n"


def test_revert_created_removes_file(tmp_path, monkeypatch):
    home = tmp_path / "home"
    ws = tmp_path / "ws"
    ws.mkdir()
    delegation_id = str(uuid.uuid4())

    _run_delegation(
        ws,
        home,
        monkeypatch,
        delegation_id=delegation_id,
        contract_paths=["new.py"],
        mutate=lambda w: (w / "new.py").write_text("x\n", encoding="utf-8"),
    )
    assert (ws / "new.py").is_file()

    reverted = revert_to_before(ws, delegation_id, ["new.py"])
    assert reverted == ["new.py"]
    assert not (ws / "new.py").exists()


def test_revert_deleted_restores_file(tmp_path, monkeypatch):
    home = tmp_path / "home"
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "gone.py").write_text("restore me\n", encoding="utf-8")
    delegation_id = str(uuid.uuid4())

    _run_delegation(
        ws,
        home,
        monkeypatch,
        delegation_id=delegation_id,
        contract_paths=["gone.py"],
        mutate=lambda w: (w / "gone.py").unlink(),
    )
    assert not (ws / "gone.py").exists()

    reverted = revert_to_before(ws, delegation_id, ["gone.py"])
    assert reverted == ["gone.py"]
    assert (ws / "gone.py").read_text(encoding="utf-8") == "restore me\n"


def test_schema_migration_from_322a_db(tmp_path):
    """Existing 322a DB without blobs/diff column upgrades cleanly."""
    ws = tmp_path / "ws"
    ws.mkdir()
    db_path = workspace_history_db_path(ws)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE snapshots (
            delegation_id TEXT PRIMARY KEY,
            mcp_session_id TEXT NOT NULL,
            timestamp_start TEXT NOT NULL,
            timestamp_end TEXT,
            spec_path TEXT,
            workspace_path TEXT NOT NULL
        );
        CREATE TABLE file_deltas (
            delegation_id TEXT NOT NULL,
            path TEXT NOT NULL,
            change_type TEXT NOT NULL,
            content_hash TEXT,
            prev_hash TEXT,
            is_binary INTEGER DEFAULT 0,
            PRIMARY KEY (delegation_id, path)
        );
        """
    )
    conn.close()

    db = WorkspaceHistoryDB(ws)
    with db._connect() as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "blobs" in tables
        cols = {
            row[1] for row in conn.execute("PRAGMA table_info(file_deltas)").fetchall()
        }
        assert "diff" in cols


def test_revert_skips_missing_blob_gracefully(tmp_path, monkeypatch):
    """Modified file revert skipped when prev_hash blob is missing."""
    home = tmp_path / "home"
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "m.py").write_text("before\n", encoding="utf-8")
    delegation_id = str(uuid.uuid4())

    _run_delegation(
        ws,
        home,
        monkeypatch,
        delegation_id=delegation_id,
        contract_paths=["m.py"],
        mutate=lambda w: (w / "m.py").write_text("after\n", encoding="utf-8"),
    )

    db_path = workspace_history_db_path(ws)
    conn = sqlite3.connect(str(db_path))
    conn.execute("DELETE FROM blobs")
    conn.commit()
    conn.close()

    reverted = revert_to_before(ws, delegation_id, ["m.py"])
    assert reverted == []
    assert (ws / "m.py").read_text(encoding="utf-8") == "after\n"

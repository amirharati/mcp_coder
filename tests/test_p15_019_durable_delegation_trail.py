"""P15-019: durable delegation trail — crash-safe snapshots.

Three pillars under test:
1. Before-manifest persisted to `manifest_files` table (durable, atomic with
   the `snapshots` INSERT).
2. Startup reconciliation pass backfills `file_deltas` + `timestamp_end` +
   `outcome='interrupted'` for orphaned delegations (`timestamp_end IS NULL`).
3. Timeout grace period + immediate outcome mark in `aider_engine.py`.

Covers acceptance criteria D1-D6 from the task spec.
"""

from __future__ import annotations

import sqlite3
import time
import uuid
from pathlib import Path
from unittest.mock import patch

# Match real runtime import order: server.mcp_server pulls in the full graph
# first, resolving the circular import between core.storage.paths and
# core.logging.server_log. See test_main_crash_handling.py for the pattern.
import server.mcp_server  # noqa: F401
from core.storage.paths import workspace_history_db_path
from core.workspace.history_db import WorkspaceHistoryDB
from core.workspace.history_query import (
    build_delegation_diff,
    list_interrupted_delegations,
)
from core.workspace.manifest import FileEntry, diff_manifests
from core.workspace.snapshot import (
    begin_delegation_snapshot,
    is_reconcile_on_startup_enabled,
    reconcile_interrupted_delegations,
    resolve_delegation_attribution,
    utc_now_iso,
)
from core.workspace.walk import walk_workspace


def _sha(data: bytes) -> str:
    import hashlib

    return hashlib.sha256(data).hexdigest()


def _entry(content: bytes, *, mtime: float = 0.0) -> FileEntry:
    return FileEntry(
        content_hash=_sha(content),
        size_bytes=len(content),
        is_binary=False,
        mtime=mtime,
    )


# ---------------------------------------------------------------------------
# D1 — Manifest persisted
# ---------------------------------------------------------------------------


def test_d1_before_manifest_persisted_and_recoverable_after_crash(tmp_path, monkeypatch):
    """D1: after begin_snapshot, the before-manifest is queryable from
    manifest_files even if the in-memory _before_manifest is dropped (crash)."""
    monkeypatch.setenv("MCP_CODER_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("MCP_CODER_DISABLE_WORKSPACE_SNAPSHOT", raising=False)

    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "a.py").write_text("alpha\n", encoding="utf-8")
    (ws / "b.py").write_text("beta\n", encoding="utf-8")

    delegation_id = str(uuid.uuid4())
    session = begin_delegation_snapshot(
        workspace_path=str(ws),
        delegation_id=delegation_id,
        mcp_session_id="sess-d1",
        timestamp_start="2026-06-29T00:00:00Z",
        spec_path="tasks/d1.md",
    )
    assert session is not None

    db = WorkspaceHistoryDB(ws)
    # Simulate a crash: drop the in-memory before-manifest.
    db._before_manifest = None
    session.before_manifest = {}

    # The before-manifest must still be recoverable from disk.
    recovered = db.get_manifest(delegation_id, role="before")
    assert set(recovered.keys()) == {"a.py", "b.py"}
    assert recovered["a.py"].content_hash == _sha(b"alpha\n")
    assert recovered["b.py"].content_hash == _sha(b"beta\n")
    assert recovered["a.py"].size_bytes == len(b"alpha\n")


def test_d1_manifest_atomic_with_snapshot_row(tmp_path, monkeypatch):
    """D1 invariant: the manifest_files INSERT is in the same conn.commit() as
    the snapshots INSERT. A snapshot row always has its manifest."""
    monkeypatch.setenv("MCP_CODER_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("MCP_CODER_DISABLE_WORKSPACE_SNAPSHOT", raising=False)

    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "keep.py").write_text("v1\n", encoding="utf-8")

    delegation_id = str(uuid.uuid4())
    begin_delegation_snapshot(
        workspace_path=str(ws),
        delegation_id=delegation_id,
        mcp_session_id="sess-atomic",
        timestamp_start="2026-06-29T00:00:00Z",
        spec_path=None,
    )

    db_path = workspace_history_db_path(ws)
    conn = sqlite3.connect(str(db_path))
    snap_count = conn.execute(
        "SELECT COUNT(*) FROM snapshots WHERE delegation_id = ?",
        (delegation_id,),
    ).fetchone()[0]
    manifest_count = conn.execute(
        "SELECT COUNT(*) FROM manifest_files WHERE delegation_id = ? AND role = 'before'",
        (delegation_id,),
    ).fetchone()[0]
    conn.close()

    assert snap_count == 1
    assert manifest_count == 1  # one row for keep.py


def test_d1_get_manifest_returns_empty_for_missing_role(tmp_path, monkeypatch):
    """D1 backward compat: get_manifest returns {} when no rows exist."""
    monkeypatch.setenv("MCP_CODER_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("MCP_CODER_DISABLE_WORKSPACE_SNAPSHOT", raising=False)

    ws = tmp_path / "ws"
    ws.mkdir()
    db = WorkspaceHistoryDB(ws)
    # No snapshot written; db file may not even exist.
    assert db.get_manifest("nonexistent", role="before") == {}
    assert db.get_manifest("nonexistent", role="after") == {}


# ---------------------------------------------------------------------------
# D2 — Startup reconciliation
# ---------------------------------------------------------------------------


def _seed_orphaned_delegation(ws: Path, home: Path, monkeypatch, *, delegation_id: str) -> None:
    """Seed a snapshots row with a before-manifest but NO commit_snapshot
    (simulate a crash mid-delegation). Then mutate the workspace so the
    reconciliation pass has something to diff."""
    monkeypatch.setenv("MCP_CODER_HOME", str(home))
    monkeypatch.delenv("MCP_CODER_DISABLE_WORKSPACE_SNAPSHOT", raising=False)

    # Before-state files.
    (ws / "modify_me.py").write_text("old\n", encoding="utf-8")
    (ws / "delete_me.py").write_text("gone\n", encoding="utf-8")

    # begin_snapshot writes snapshots row + manifest_files(before) + blobs.
    session = begin_delegation_snapshot(
        workspace_path=str(ws),
        delegation_id=delegation_id,
        mcp_session_id="sess-d2",
        timestamp_start="2026-06-29T00:00:00Z",
        spec_path="tasks/d2.md",
    )
    assert session is not None

    # Simulate the executor doing work, then the process dying before
    # commit_snapshot runs.
    (ws / "modify_me.py").write_text("new\n", encoding="utf-8")
    (ws / "delete_me.py").unlink()
    (ws / "create_me.py").write_text("fresh\n", encoding="utf-8")

    # Drop in-memory state (process restart).
    session.history_db._before_manifest = None
    session.before_manifest = {}


def test_d2_reconciliation_backfills_orphaned_delegation(tmp_path, monkeypatch):
    """D2: seed before-manifest + write files + simulate crash (no
    commit_snapshot) → reconcile → get_delegation_diff returns correct
    created/modified/deleted."""
    home = tmp_path / "home"
    ws = tmp_path / "ws"
    ws.mkdir()
    delegation_id = str(uuid.uuid4())
    _seed_orphaned_delegation(ws, home, monkeypatch, delegation_id=delegation_id)

    # Before reconciliation: row is orphaned.
    interrupted = list_interrupted_delegations(ws)
    assert len(interrupted) == 1
    assert interrupted[0]["delegation_id"] == delegation_id
    assert interrupted[0]["has_before_manifest"] is True

    snapshots_before = WorkspaceHistoryDB(ws).get_snapshot(delegation_id)
    assert snapshots_before["timestamp_end"] is None
    assert snapshots_before["outcome"] is None

    # Run reconciliation.
    summaries = reconcile_interrupted_delegations(str(ws))
    assert len(summaries) == 1
    summary = summaries[0]
    assert summary["delegation_id"] == delegation_id
    assert summary["outcome"] == "interrupted"
    assert summary["created"] == ["create_me.py"]
    assert summary["modified"] == ["modify_me.py"]
    assert summary["deleted"] == ["delete_me.py"]

    # After reconciliation: row is finalized.
    snap = WorkspaceHistoryDB(ws).get_snapshot(delegation_id)
    assert snap["timestamp_end"] is not None
    assert snap["outcome"] == "interrupted"

    # get_delegation_diff returns the correct diff.
    diff = build_delegation_diff(ws, delegation_id)
    assert diff is not None
    assert diff.created == ["create_me.py"]
    assert diff.modified == ["modify_me.py"]
    assert diff.deleted == ["delete_me.py"]
    assert diff.timestamp_end is not None


def test_d2_reconciliation_persists_after_manifest(tmp_path, monkeypatch):
    """D2: reconciliation also persists after-manifest rows for created/modified."""
    home = tmp_path / "home"
    ws = tmp_path / "ws"
    ws.mkdir()
    delegation_id = str(uuid.uuid4())
    _seed_orphaned_delegation(ws, home, monkeypatch, delegation_id=delegation_id)

    reconcile_interrupted_delegations(str(ws))

    db = WorkspaceHistoryDB(ws)
    after = db.get_manifest(delegation_id, role="after")
    # create_me.py and modify_me.py are created/modified → in after-manifest.
    assert "create_me.py" in after
    assert "modify_me.py" in after
    assert after["create_me.py"].content_hash == _sha(b"fresh\n")
    assert after["modify_me.py"].content_hash == _sha(b"new\n")
    # delete_me.py is deleted → NOT in after-manifest.
    assert "delete_me.py" not in after


def test_d2_reconciliation_no_op_when_no_orphans(tmp_path, monkeypatch):
    """D2: reconciliation returns [] when there are no orphaned delegations."""
    monkeypatch.setenv("MCP_CODER_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("MCP_CODER_DISABLE_WORKSPACE_SNAPSHOT", raising=False)

    ws = tmp_path / "ws"
    ws.mkdir()
    # No DB at all.
    summaries = reconcile_interrupted_delegations(str(ws))
    assert summaries == []


# ---------------------------------------------------------------------------
# D3 — Idempotent & failure-tolerant
# ---------------------------------------------------------------------------


def test_d3_reconciliation_idempotent(tmp_path, monkeypatch):
    """D3: reconciling twice produces no duplicate file_deltas rows."""
    home = tmp_path / "home"
    ws = tmp_path / "ws"
    ws.mkdir()
    delegation_id = str(uuid.uuid4())
    _seed_orphaned_delegation(ws, home, monkeypatch, delegation_id=delegation_id)

    # First pass.
    summaries1 = reconcile_interrupted_delegations(str(ws))
    assert len(summaries1) == 1

    # Second pass: no orphans remain (timestamp_end now set), so nothing to do.
    summaries2 = reconcile_interrupted_delegations(str(ws))
    assert summaries2 == []

    # No duplicate file_deltas rows.
    db = WorkspaceHistoryDB(ws)
    deltas = db.get_file_deltas(delegation_id)
    assert len(deltas) == 3  # create_me, modify_me, delete_me
    paths = {d["path"] for d in deltas}
    assert paths == {"create_me.py", "modify_me.py", "delete_me.py"}


def test_d3_reconciliation_failure_tolerant(tmp_path, monkeypatch):
    """D3: a corrupted delegation row does not crash the pass; it is skipped
    with a warning and the others are still reconciled."""
    home = tmp_path / "home"
    monkeypatch.setenv("MCP_CODER_HOME", str(home))
    monkeypatch.delenv("MCP_CODER_DISABLE_WORKSPACE_SNAPSHOT", raising=False)

    ws = tmp_path / "ws"
    ws.mkdir()

    # Seed two valid orphaned delegations.
    did_good1 = str(uuid.uuid4())
    _seed_orphaned_delegation(ws, home, monkeypatch, delegation_id=did_good1)

    did_good2 = str(uuid.uuid4())
    # Reset workspace state for the second delegation: the before-manifest for
    # did_good2 will be the current workspace (post-good1-mutation).
    session2 = begin_delegation_snapshot(
        workspace_path=str(ws),
        delegation_id=did_good2,
        mcp_session_id="sess-d3-2",
        timestamp_start="2026-06-29T01:00:00Z",
        spec_path="tasks/d3b.md",
    )
    assert session2 is not None
    session2.history_db._before_manifest = None
    session2.before_manifest = {}

    # Mutate again so did_good2 has a diff.
    (ws / "second_create.py").write_text("second\n", encoding="utf-8")

    # Corrupt did_good2's manifest_files so its reconciliation raises: delete
    # all manifest rows for it, making it a "legacy" row that gets skipped.
    db_path = workspace_history_db_path(ws)
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "DELETE FROM manifest_files WHERE delegation_id = ?", (did_good2,)
    )
    conn.commit()
    conn.close()

    # Reconciliation should skip did_good2 (legacy / no manifest) and still
    # reconcile did_good1.
    summaries = reconcile_interrupted_delegations(str(ws))
    reconciled_ids = {s["delegation_id"] for s in summaries}
    assert did_good1 in reconciled_ids
    assert did_good2 not in reconciled_ids  # skipped, not crashed

    # did_good1 got finalized; did_good2 is still orphaned (skipped).
    db = WorkspaceHistoryDB(ws)
    snap1 = db.get_snapshot(did_good1)
    assert snap1["outcome"] == "interrupted"
    snap2 = db.get_snapshot(did_good2)
    assert snap2["timestamp_end"] is None  # still orphaned


def test_d3_reconciliation_walk_failure_returns_empty(tmp_path, monkeypatch):
    """D3: if the workspace walk itself fails, reconciliation returns [] and
    logs rather than crashing."""
    home = tmp_path / "home"
    ws = tmp_path / "ws"
    ws.mkdir()
    delegation_id = str(uuid.uuid4())
    _seed_orphaned_delegation(ws, home, monkeypatch, delegation_id=delegation_id)

    def boom(_path: str):
        raise OSError("disk read failure")

    with patch("core.workspace.snapshot.walk_workspace", side_effect=boom):
        summaries = reconcile_interrupted_delegations(str(ws))
    assert summaries == []
    # The orphan is still there (not reconciled).
    assert len(list_interrupted_delegations(ws)) == 1


# ---------------------------------------------------------------------------
# D4 — Legacy compat
# ---------------------------------------------------------------------------


def test_d4_legacy_row_without_manifest_skipped(tmp_path, monkeypatch):
    """D4: a snapshots row with no manifest_files entries (pre-P15-019) is
    skipped gracefully by reconciliation (no error, no crash)."""
    home = tmp_path / "home"
    monkeypatch.setenv("MCP_CODER_HOME", str(home))
    monkeypatch.delenv("MCP_CODER_DISABLE_WORKSPACE_SNAPSHOT", raising=False)

    ws = tmp_path / "ws"
    ws.mkdir()

    # Manually insert a legacy snapshot row (no manifest_files entries).
    db_path = workspace_history_db_path(ws)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS snapshots (
            delegation_id TEXT PRIMARY KEY,
            mcp_session_id TEXT NOT NULL,
            timestamp_start TEXT NOT NULL,
            timestamp_end TEXT,
            spec_path TEXT,
            workspace_path TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS file_deltas (
            delegation_id TEXT NOT NULL,
            path TEXT NOT NULL,
            change_type TEXT NOT NULL,
            content_hash TEXT,
            prev_hash TEXT,
            is_binary INTEGER DEFAULT 0,
            diff TEXT,
            PRIMARY KEY (delegation_id, path)
        );
        CREATE TABLE IF NOT EXISTS blobs (
            hash TEXT PRIMARY KEY,
            content BLOB NOT NULL
        );
        CREATE TABLE IF NOT EXISTS manifest_files (
            delegation_id TEXT NOT NULL,
            path TEXT NOT NULL,
            content_hash TEXT,
            size_bytes INTEGER,
            is_binary INTEGER DEFAULT 0,
            mtime REAL,
            role TEXT NOT NULL DEFAULT 'before',
            PRIMARY KEY (delegation_id, path, role)
        );
        """
    )
    legacy_id = "legacy-delegation-0001"
    conn.execute(
        """
        INSERT INTO snapshots (delegation_id, mcp_session_id, timestamp_start,
                               workspace_path)
        VALUES (?, ?, ?, ?)
        """,
        (legacy_id, "sess-legacy", "2026-06-01T00:00:00Z", str(ws)),
    )
    conn.commit()
    conn.close()

    # Reconciliation should skip the legacy row (no manifest) without error.
    summaries = reconcile_interrupted_delegations(str(ws))
    assert summaries == []

    # The legacy row is still orphaned (untouched).
    db = WorkspaceHistoryDB(ws)
    snap = db.get_snapshot(legacy_id)
    assert snap["timestamp_end"] is None


# ---------------------------------------------------------------------------
# D5 — Timeout grace period
# ---------------------------------------------------------------------------


def test_d5_executor_flush_grace_seconds_default(monkeypatch):
    """D5: default grace period is 5.0s."""
    monkeypatch.delenv("MCP_CODER_EXECUTOR_FLUSH_GRACE_S", raising=False)
    from core.engine.aider_engine import _executor_flush_grace_seconds

    assert _executor_flush_grace_seconds() == 5.0


def test_d5_executor_flush_grace_seconds_env_override(monkeypatch):
    """D5: grace period is tunable via MCP_CODER_EXECUTOR_FLUSH_GRACE_S."""
    monkeypatch.setenv("MCP_CODER_EXECUTOR_FLUSH_GRACE_S", "0.25")
    from core.engine.aider_engine import _executor_flush_grace_seconds

    assert _executor_flush_grace_seconds() == 0.25


def test_d5_grace_period_lets_executor_flush_before_kill(tmp_path, monkeypatch):
    """D5 (B014 fix): on timeout, the executor thread gets the grace window to
    flush buffered writes. A mock executor that writes a file during the grace
    window → after-walk sees the file (not just cache files)."""
    monkeypatch.setenv("MCP_CODER_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("MCP_CODER_DISABLE_WORKSPACE_SNAPSHOT", raising=False)
    # Short timeout so the test runs fast; grace window longer than the write.
    monkeypatch.setenv("MCP_CODER_EXECUTOR_FLUSH_GRACE_S", "2.0")
    monkeypatch.setenv("MCP_CODER_DELEGATION_TIMEOUT_S", "0.1")

    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "existing.py").write_text("v1\n", encoding="utf-8")

    delegation_id = str(uuid.uuid4())
    session = begin_delegation_snapshot(
        workspace_path=str(ws),
        delegation_id=delegation_id,
        mcp_session_id="sess-d5",
        timestamp_start="2026-06-29T00:00:00Z",
        spec_path="tasks/d5.md",
    )
    assert session is not None

    # Simulate the executor: sleep past the timeout, then write a file during
    # the grace window. The grace-period shutdown waits for this to finish.
    def _mock_run_coder():
        time.sleep(0.3)  # past the 0.1s timeout, within the 2.0s grace window
        (ws / "grace_written.py").write_text("flushed\n", encoding="utf-8")
        return None, None, None, "", False, False

    import concurrent.futures
    import contextvars

    pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    ctx = contextvars.copy_context()
    future = pool.submit(ctx.run, _mock_run_coder)

    # Trigger the timeout path.
    try:
        future.result(timeout=0.1)
        raised = False
    except concurrent.futures.TimeoutError:
        raised = True
    assert raised

    # P15-019: grace-period shutdown lets the flush land.
    from core.engine.aider_engine import _shutdown_pool_with_grace

    _shutdown_pool_with_grace(pool, future)

    # The file written during the grace window is on disk.
    assert (ws / "grace_written.py").is_file()
    assert (ws / "grace_written.py").read_text(encoding="utf-8") == "flushed\n"


def test_d5_grace_period_zero_kills_instantly(tmp_path, monkeypatch):
    """D5: when grace=0, the executor is killed instantly (legacy behavior)."""
    monkeypatch.setenv("MCP_CODER_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("MCP_CODER_DISABLE_WORKSPACE_SNAPSHOT", raising=False)
    monkeypatch.setenv("MCP_CODER_EXECUTOR_FLUSH_GRACE_S", "0")

    ws = tmp_path / "ws"
    ws.mkdir()

    import concurrent.futures
    import contextvars

    written = {"done": False}

    def _slow_run():
        time.sleep(2.0)
        written["done"] = True
        return None

    pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    ctx = contextvars.copy_context()
    future = pool.submit(ctx.run, _slow_run)

    try:
        future.result(timeout=0.05)
    except concurrent.futures.TimeoutError:
        pass

    from core.engine.aider_engine import _shutdown_pool_with_grace

    t0 = time.monotonic()
    _shutdown_pool_with_grace(pool, future)
    elapsed = time.monotonic() - t0

    # With grace=0, shutdown returns near-instantly (did NOT wait 2s for thread).
    assert elapsed < 1.0
    # The thread was killed before it could finish.
    assert written["done"] is False


# ---------------------------------------------------------------------------
# D6 — Outcome marked on all abnormal paths
# ---------------------------------------------------------------------------


def test_d6_mark_outcome_writes_outcome_and_timestamp_end(tmp_path, monkeypatch):
    """D6: WorkspaceHistoryDB.mark_outcome sets outcome + timestamp_end."""
    home = tmp_path / "home"
    monkeypatch.setenv("MCP_CODER_HOME", str(home))
    monkeypatch.delenv("MCP_CODER_DISABLE_WORKSPACE_SNAPSHOT", raising=False)

    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "a.py").write_text("v1\n", encoding="utf-8")
    delegation_id = str(uuid.uuid4())

    session = begin_delegation_snapshot(
        workspace_path=str(ws),
        delegation_id=delegation_id,
        mcp_session_id="sess-d6",
        timestamp_start="2026-06-29T00:00:00Z",
        spec_path=None,
    )
    assert session is not None
    assert session.history_db is not None

    # Before mark: outcome is None, timestamp_end is None.
    db = WorkspaceHistoryDB(ws)
    snap = db.get_snapshot(delegation_id)
    assert snap["outcome"] is None
    assert snap["timestamp_end"] is None

    # Mark outcome (as the timeout path does).
    session.history_db.mark_outcome(
        delegation_id, outcome="timeout", timestamp_end=utc_now_iso()
    )

    snap = db.get_snapshot(delegation_id)
    assert snap["outcome"] == "timeout"
    assert snap["timestamp_end"] is not None


def test_d6_mark_outcome_idempotent(tmp_path, monkeypatch):
    """D6: mark_outcome is safe to call multiple times."""
    home = tmp_path / "home"
    monkeypatch.setenv("MCP_CODER_HOME", str(home))
    monkeypatch.delenv("MCP_CODER_DISABLE_WORKSPACE_SNAPSHOT", raising=False)

    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "a.py").write_text("v1\n", encoding="utf-8")
    delegation_id = str(uuid.uuid4())

    session = begin_delegation_snapshot(
        workspace_path=str(ws),
        delegation_id=delegation_id,
        mcp_session_id="sess-d6-idem",
        timestamp_start="2026-06-29T00:00:00Z",
        spec_path=None,
    )
    assert session is not None

    db = session.history_db
    # Calling twice does not raise.
    db.mark_outcome(delegation_id, outcome="timeout", timestamp_end=utc_now_iso())
    db.mark_outcome(delegation_id, outcome="timeout", timestamp_end=utc_now_iso())

    snap = WorkspaceHistoryDB(ws).get_snapshot(delegation_id)
    assert snap["outcome"] == "timeout"


def test_d6_mark_outcome_no_db_file_is_noop(tmp_path, monkeypatch):
    """D6: mark_outcome is a no-op when the DB file doesn't exist yet."""
    monkeypatch.setenv("MCP_CODER_HOME", str(tmp_path / "home"))
    db = WorkspaceHistoryDB(str(tmp_path / "nowhere"))
    # Should not raise.
    db.mark_outcome("nonexistent", outcome="timeout", timestamp_end="now")


def test_d6_mark_delegation_outcome_helper_tolerates_missing_session(tmp_path, monkeypatch):
    """D6: the _mark_delegation_outcome helper is a no-op when snapshot_session
    is None or has no history_db (must not mask the original failure)."""
    from core.engine.aider_engine import _mark_delegation_outcome

    # None session → no-op.
    _mark_delegation_outcome("did", None, outcome="timeout")

    # Session with no history_db → no-op.
    class _BareSession:
        history_db = None

    _mark_delegation_outcome("did", _BareSession(), outcome="timeout")

    # None delegation_id → no-op.
    _mark_delegation_outcome(None, _BareSession(), outcome="timeout")


# ---------------------------------------------------------------------------
# Reconcile-on-startup flag
# ---------------------------------------------------------------------------


def test_reconcile_on_startup_enabled_default(monkeypatch):
    """MCP_CODER_RECONCILE_ON_STARTUP defaults to on."""
    monkeypatch.delenv("MCP_CODER_RECONCILE_ON_STARTUP", raising=False)
    assert is_reconcile_on_startup_enabled() is True


def test_reconcile_on_startup_disabled(monkeypatch):
    """MCP_CODER_RECONCILE_ON_STARTUP=0 disables the pass."""
    monkeypatch.setenv("MCP_CODER_RECONCILE_ON_STARTUP", "0")
    assert is_reconcile_on_startup_enabled() is False


def test_reconcile_on_startup_enabled_explicit(monkeypatch):
    """MCP_CODER_RECONCILE_ON_STARTUP=1 enables the pass."""
    monkeypatch.setenv("MCP_CODER_RECONCILE_ON_STARTUP", "1")
    assert is_reconcile_on_startup_enabled() is True


# ---------------------------------------------------------------------------
# Regression: P15-019-R1 — begin_snapshot called twice on same delegation_id
# ---------------------------------------------------------------------------


def test_begin_snapshot_idempotent_on_retry(tmp_path, monkeypatch):
    """Regression P15-019-R1: begin_snapshot must not raise UNIQUE constraint
    error when called twice with the same delegation_id.

    Root cause: the P15-ISS-010 retry loop calls engine.run() multiple times
    with the same delegation_id. Each call to engine.run() calls
    begin_delegation_snapshot() → begin_snapshot() → INSERT INTO snapshots.
    The second call crashed with IntegrityError: UNIQUE constraint failed:
    snapshots.delegation_id.

    Fix: INSERT OR IGNORE in begin_snapshot() so retries are safe.
    """
    monkeypatch.setenv("MCP_CODER_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("MCP_CODER_DISABLE_WORKSPACE_SNAPSHOT", raising=False)

    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "a.py").write_text("v1\n", encoding="utf-8")

    delegation_id = str(uuid.uuid4())
    db = WorkspaceHistoryDB(ws)

    # First call — simulates turn 1 of the retry loop.
    before = walk_workspace(str(ws))
    db.begin_snapshot(
        delegation_id=delegation_id,
        mcp_session_id="sess-retry",
        timestamp_start="2026-06-29T10:00:00Z",
        spec_path="tasks/retry.md",
        before_manifest=before,
    )

    # Second call with the same delegation_id — simulates turn 2 of the retry
    # loop. Must NOT raise IntegrityError.
    (ws / "a.py").write_text("v2\n", encoding="utf-8")
    before2 = walk_workspace(str(ws))
    db.begin_snapshot(
        delegation_id=delegation_id,
        mcp_session_id="sess-retry",
        timestamp_start="2026-06-29T10:01:00Z",
        spec_path="tasks/retry.md",
        before_manifest=before2,
    )

    # The snapshot row exists exactly once.
    rows = db.list_snapshots(limit=10)
    assert sum(1 for r in rows if r["delegation_id"] == delegation_id) == 1

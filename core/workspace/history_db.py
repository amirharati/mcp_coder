from __future__ import annotations

import sqlite3
from pathlib import Path

from core.engine.git_diff import normalize_repo_path
from core.workspace.diff_util import unified_diff_text
from core.workspace.manifest import DelegationDelta, FileEntry, Manifest
from core.workspace.walk import (
    is_binary_content,
    max_file_bytes,
    read_workspace_file,
    sha256_bytes,
)


def _history_db_path(workspace: str | Path) -> Path:
    from core.storage.paths import workspace_history_db_path

    return workspace_history_db_path(workspace)


_SNAPSHOT_CHECKPOINT_COLUMNS: tuple[tuple[str, str], ...] = (
    ("checkpoint_summary", "TEXT"),
    ("delegate_mode", "TEXT"),
    ("outcome", "TEXT"),
    ("model", "TEXT"),
    ("duration_ms", "INTEGER"),
    ("tokens_total", "INTEGER"),
    ("error_class", "TEXT"),
    ("delta_created", "INTEGER"),
    ("delta_modified", "INTEGER"),
    ("delta_deleted", "INTEGER"),
    ("spec_report_path", "TEXT"),
)

_SNAPSHOT_COLUMNS = """
    delegation_id, mcp_session_id, timestamp_start, timestamp_end, spec_path,
    workspace_path, checkpoint_summary, delegate_mode, outcome, model,
    duration_ms, tokens_total, error_class, delta_created, delta_modified,
    delta_deleted, spec_report_path
"""

_SNAPSHOT_SELECT = _SNAPSHOT_COLUMNS

_SNAPSHOT_SELECT_S = """
    s.delegation_id, s.mcp_session_id, s.timestamp_start, s.timestamp_end, s.spec_path,
    s.workspace_path, s.checkpoint_summary, s.delegate_mode, s.outcome, s.model,
    s.duration_ms, s.tokens_total, s.error_class, s.delta_created, s.delta_modified,
    s.delta_deleted, s.spec_report_path
"""


class WorkspaceHistoryDB:
    """SQLite persistence for delegation workspace snapshots + content blobs."""

    def __init__(self, workspace: str | Path) -> None:
        self.workspace = str(Path(workspace).resolve())
        self.db_path = _history_db_path(workspace)
        self._before_manifest: Manifest | None = None

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("PRAGMA journal_mode=WAL")
        self._init_schema(conn)
        return conn

    @staticmethod
    def _init_schema(conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS snapshots (
                delegation_id   TEXT PRIMARY KEY,
                mcp_session_id  TEXT NOT NULL,
                timestamp_start TEXT NOT NULL,
                timestamp_end   TEXT,
                spec_path       TEXT,
                workspace_path  TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS file_deltas (
                delegation_id TEXT NOT NULL,
                path          TEXT NOT NULL,
                change_type   TEXT NOT NULL,
                content_hash  TEXT,
                prev_hash     TEXT,
                is_binary     INTEGER DEFAULT 0,
                diff          TEXT,
                PRIMARY KEY (delegation_id, path)
            );

            CREATE TABLE IF NOT EXISTS blobs (
                hash    TEXT PRIMARY KEY,
                content BLOB NOT NULL
            );

            CREATE TABLE IF NOT EXISTS manifest_files (
                delegation_id TEXT NOT NULL,
                path          TEXT NOT NULL,
                content_hash  TEXT,
                size_bytes    INTEGER,
                is_binary     INTEGER DEFAULT 0,
                mtime         REAL,
                role          TEXT NOT NULL DEFAULT 'before',
                PRIMARY KEY (delegation_id, path, role)
            );
            """
        )
        cols = {
            row[1] for row in conn.execute("PRAGMA table_info(file_deltas)").fetchall()
        }
        if "diff" not in cols:
            conn.execute("ALTER TABLE file_deltas ADD COLUMN diff TEXT")
        WorkspaceHistoryDB._migrate_snapshot_checkpoint_columns(conn)

    @staticmethod
    def _migrate_snapshot_checkpoint_columns(conn: sqlite3.Connection) -> None:
        cols = {
            row[1] for row in conn.execute("PRAGMA table_info(snapshots)").fetchall()
        }
        for name, sql_type in _SNAPSHOT_CHECKPOINT_COLUMNS:
            if name not in cols:
                conn.execute(f"ALTER TABLE snapshots ADD COLUMN {name} {sql_type}")

    @staticmethod
    def _insert_blob(conn: sqlite3.Connection, data: bytes) -> str:
        content_hash = sha256_bytes(data)
        conn.execute(
            "INSERT OR IGNORE INTO blobs (hash, content) VALUES (?, ?)",
            (content_hash, data),
        )
        return content_hash

    @staticmethod
    def get_blob_content(conn: sqlite3.Connection, content_hash: str) -> bytes | None:
        row = conn.execute(
            "SELECT content FROM blobs WHERE hash = ?",
            (content_hash,),
        ).fetchone()
        return row[0] if row else None

    def _store_before_manifest_blobs(
        self, conn: sqlite3.Connection, before_manifest: Manifest
    ) -> None:
        root = Path(self.workspace)
        limit = max_file_bytes()
        for path, entry in before_manifest.items():
            if entry.is_binary:
                continue
            abs_path = root / path
            try:
                if not abs_path.is_file():
                    continue
                data = abs_path.read_bytes()
            except OSError:
                continue
            if len(data) > limit:
                continue
            self._insert_blob(conn, data)

    @staticmethod
    def _store_manifest_rows(
        conn: sqlite3.Connection,
        delegation_id: str,
        manifest: Manifest,
        role: str,
    ) -> None:
        """Persist path->hash map into manifest_files (idempotent via PRIMARY KEY)."""
        for path, entry in manifest.items():
            conn.execute(
                """
                INSERT OR REPLACE INTO manifest_files (
                    delegation_id, path, content_hash, size_bytes,
                    is_binary, mtime, role
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    delegation_id,
                    path,
                    entry.content_hash,
                    entry.size_bytes,
                    int(entry.is_binary),
                    entry.mtime,
                    role,
                ),
            )

    def _snapshot_contract_paths(
        self,
        conn: sqlite3.Connection,
        contract_paths: list[str] | None,
    ) -> int:
        if not contract_paths:
            return 0
        snapshotted = 0
        seen: set[str] = set()
        for raw in contract_paths:
            path = normalize_repo_path(raw)
            if not path or path in seen:
                continue
            seen.add(path)
            data = read_workspace_file(self.workspace, path)
            if data is None or is_binary_content(data):
                continue
            self._insert_blob(conn, data)
            snapshotted += 1
        return snapshotted

    def begin_snapshot(
        self,
        *,
        delegation_id: str,
        mcp_session_id: str,
        timestamp_start: str,
        spec_path: str | None,
        before_manifest: Manifest,
        contract_paths: list[str] | None = None,
    ) -> dict[str, int]:
        self._before_manifest = before_manifest
        with self._connect() as conn:
            self._store_before_manifest_blobs(conn, before_manifest)
            contract_snapshotted = self._snapshot_contract_paths(conn, contract_paths)
            # P15-019: persist the before-manifest in the SAME transaction as the
            # snapshots INSERT so a crash mid-begin leaves both or neither.
            self._store_manifest_rows(
                conn, delegation_id, before_manifest, role="before"
            )
            conn.execute(
                """
                INSERT INTO snapshots (
                    delegation_id, mcp_session_id, timestamp_start,
                    spec_path, workspace_path
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    delegation_id,
                    mcp_session_id,
                    timestamp_start,
                    spec_path,
                    self.workspace,
                ),
            )
            conn.commit()
        return {"contract_paths_snapshotted": contract_snapshotted}

    def _write_delta_rows(
        self,
        conn: sqlite3.Connection,
        *,
        delegation_id: str,
        delta: DelegationDelta,
        after_manifest: Manifest,
        before: Manifest,
    ) -> int:
        """Write file_deltas + after-blobs for a delta. Shared by commit_snapshot
        and reconciliation. Returns diffs_stored count."""
        diffs_stored = 0
        for path in delta.created:
            entry = after_manifest[path]
            diff_text: str | None = None
            if not entry.is_binary:
                after_data = read_workspace_file(self.workspace, path)
                if after_data is not None:
                    self._insert_blob(conn, after_data)
            conn.execute(
                """
                INSERT INTO file_deltas (
                    delegation_id, path, change_type,
                    content_hash, prev_hash, is_binary, diff
                ) VALUES (?, ?, 'created', ?, NULL, ?, ?)
                """,
                (
                    delegation_id,
                    path,
                    entry.content_hash,
                    int(entry.is_binary),
                    diff_text,
                ),
            )

        for path in delta.modified:
            after_entry = after_manifest[path]
            before_entry = before[path]
            diff_text = None
            if not after_entry.is_binary and not before_entry.is_binary:
                before_data = self.get_blob_content(conn, before_entry.content_hash)
                after_data = read_workspace_file(self.workspace, path)
                if before_data is not None and after_data is not None:
                    self._insert_blob(conn, after_data)
                    diff_text = unified_diff_text(path, before_data, after_data)
                    if diff_text:
                        diffs_stored += 1
            conn.execute(
                """
                INSERT INTO file_deltas (
                    delegation_id, path, change_type,
                    content_hash, prev_hash, is_binary, diff
                ) VALUES (?, ?, 'modified', ?, ?, ?, ?)
                """,
                (
                    delegation_id,
                    path,
                    after_entry.content_hash,
                    before_entry.content_hash,
                    int(after_entry.is_binary),
                    diff_text,
                ),
            )

        for path in delta.deleted:
            before_entry = before[path]
            conn.execute(
                """
                INSERT INTO file_deltas (
                    delegation_id, path, change_type,
                    content_hash, prev_hash, is_binary, diff
                ) VALUES (?, ?, 'deleted', NULL, ?, ?, NULL)
                """,
                (
                    delegation_id,
                    path,
                    before_entry.content_hash,
                    int(before_entry.is_binary),
                ),
            )
        return diffs_stored

    def commit_snapshot(
        self,
        *,
        delegation_id: str,
        timestamp_end: str,
        delta: DelegationDelta,
        after_manifest: Manifest,
    ) -> dict[str, int]:
        before = self._before_manifest or {}
        # P15-019: persist the after-manifest for created/modified paths in the
        # same transaction as the file_deltas + timestamp_end UPDATE.
        after_manifest_to_persist: Manifest = {
            path: after_manifest[path]
            for path in (*delta.created, *delta.modified)
            if path in after_manifest
        }
        with self._connect() as conn:
            self._store_manifest_rows(
                conn, delegation_id, after_manifest_to_persist, role="after"
            )
            conn.execute(
                "UPDATE snapshots SET timestamp_end = ? WHERE delegation_id = ?",
                (timestamp_end, delegation_id),
            )
            diffs_stored = self._write_delta_rows(
                conn,
                delegation_id=delegation_id,
                delta=delta,
                after_manifest=after_manifest,
                before=before,
            )
            conn.commit()
        return {"diffs_stored": diffs_stored}

    def _reconcile_commit_snapshot(
        self,
        *,
        delegation_id: str,
        timestamp_end: str,
        delta: DelegationDelta,
        after_manifest: Manifest,
        before_manifest: Manifest,
    ) -> dict[str, int]:
        """P15-019: commit_snapshot-equivalent for the reconciliation pass.

        Differences from commit_snapshot:
        - Takes before_manifest explicitly (in-memory _before_manifest is gone
          after a restart).
        - DELETEs existing file_deltas first so a second reconciliation pass
          is idempotent (no duplicate PK violation).
        - Sets outcome='interrupted' in addition to timestamp_end.
        - Persists after-manifest rows for created/modified paths.
        """
        after_manifest_to_persist: Manifest = {
            path: after_manifest[path]
            for path in (*delta.created, *delta.modified)
            if path in after_manifest
        }
        with self._connect() as conn:
            self._store_manifest_rows(
                conn, delegation_id, after_manifest_to_persist, role="after"
            )
            # Idempotency: clear any prior file_deltas so a second reconciliation
            # pass can re-insert without a PK violation.
            conn.execute(
                "DELETE FROM file_deltas WHERE delegation_id = ?",
                (delegation_id,),
            )
            conn.execute(
                """
                UPDATE snapshots
                SET timestamp_end = ?, outcome = 'interrupted'
                WHERE delegation_id = ?
                """,
                (timestamp_end, delegation_id),
            )
            diffs_stored = self._write_delta_rows(
                conn,
                delegation_id=delegation_id,
                delta=delta,
                after_manifest=after_manifest,
                before=before_manifest,
            )
            conn.commit()
        return {"diffs_stored": diffs_stored}

    def get_file_deltas(self, delegation_id: str) -> list[dict[str, object]]:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT path, change_type, content_hash, prev_hash, is_binary, diff
                FROM file_deltas
                WHERE delegation_id = ?
                ORDER BY path
                """,
                (delegation_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_file_delta(self, delegation_id: str, path: str) -> dict[str, object] | None:
        rel = normalize_repo_path(path)
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT path, change_type, content_hash, prev_hash, is_binary, diff
                FROM file_deltas
                WHERE delegation_id = ? AND path = ?
                """,
                (delegation_id, rel),
            ).fetchone()
        return dict(row) if row else None

    def get_manifest(
        self,
        delegation_id: str,
        role: str = "before",
    ) -> Manifest:
        """Reconstruct a Manifest dict from the manifest_files table.

        P15-019: lets recovery code diff current_workspace - before_manifest even
        after a hard crash. Returns {} when no rows exist (legacy / pre-P15-019).
        """
        if not self.db_path.is_file():
            return {}
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT path, content_hash, size_bytes, is_binary, mtime
                FROM manifest_files
                WHERE delegation_id = ? AND role = ?
                """,
                (delegation_id, role),
            ).fetchall()
        manifest: Manifest = {}
        for path, content_hash, size_bytes, is_binary, mtime in rows:
            if not path or not content_hash:
                continue
            manifest[str(path)] = FileEntry(
                content_hash=str(content_hash),
                size_bytes=int(size_bytes) if size_bytes is not None else 0,
                is_binary=bool(is_binary),
                mtime=float(mtime) if mtime is not None else 0.0,
            )
        return manifest

    def mark_outcome(
        self,
        delegation_id: str,
        *,
        outcome: str,
        timestamp_end: str | None = None,
    ) -> None:
        """P15-019: immediately mark a snapshot row's outcome + timestamp_end.

        Called from the timeout/abort/exception paths in aider_engine.py BEFORE
        doing anything else, so the row is never left in limbo
        (timestamp_end=NULL) even if subsequent steps fail. Safe to call multiple
        times (idempotent UPDATE); later calls overwrite earlier outcomes only
        when timestamp_end was previously NULL.
        """
        if not self.db_path.is_file():
            return
        with self._connect() as conn:
            if timestamp_end is not None:
                conn.execute(
                    """
                    UPDATE snapshots
                    SET outcome = ?, timestamp_end = ?
                    WHERE delegation_id = ?
                    """,
                    (outcome, timestamp_end, delegation_id),
                )
            else:
                conn.execute(
                    """
                    UPDATE snapshots
                    SET outcome = ?
                    WHERE delegation_id = ?
                    """,
                    (outcome, delegation_id),
                )
            conn.commit()

    def fetch_blob(self, content_hash: str) -> bytes | None:
        with self._connect() as conn:
            return self.get_blob_content(conn, content_hash)

    def get_snapshot(self, delegation_id: str) -> dict[str, object] | None:
        if not self.db_path.is_file():
            return None
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                f"""
                SELECT {_SNAPSHOT_SELECT}
                FROM snapshots
                WHERE delegation_id = ?
                """,
                (delegation_id,),
            ).fetchone()
        return dict(row) if row else None

    def finalize_checkpoint_metadata(
        self,
        *,
        delegation_id: str,
        checkpoint_summary: str,
        delegate_mode: str | None,
        outcome: str | None,
        model: str | None,
        duration_ms: int | None,
        tokens_total: int | None,
        error_class: str | None,
        delta_created: int,
        delta_modified: int,
        delta_deleted: int,
        spec_report_path: str | None = None,
    ) -> None:
        if not self.db_path.is_file():
            return
        with self._connect() as conn:
            cur = conn.execute(
                """
                UPDATE snapshots SET
                    checkpoint_summary = ?,
                    delegate_mode = ?,
                    outcome = ?,
                    model = ?,
                    duration_ms = ?,
                    tokens_total = ?,
                    error_class = ?,
                    delta_created = ?,
                    delta_modified = ?,
                    delta_deleted = ?,
                    spec_report_path = ?
                WHERE delegation_id = ?
                """,
                (
                    checkpoint_summary,
                    delegate_mode,
                    outcome,
                    model,
                    duration_ms,
                    tokens_total,
                    error_class,
                    delta_created,
                    delta_modified,
                    delta_deleted,
                    spec_report_path,
                    delegation_id,
                ),
            )
            conn.commit()
            if cur.rowcount == 0:
                return

    def get_latest_delegation_id(self) -> str | None:
        rows = self.list_snapshots(limit=1)
        if not rows:
            return None
        return str(rows[0]["delegation_id"])

    def list_interrupted_snapshots(self) -> list[dict[str, object]]:
        """P15-019: return snapshots rows with timestamp_end IS NULL.

        These are orphaned delegations (crash mid-run) that the startup
        reconciliation pass must backfill. Returns [] when the DB doesn't exist.
        """
        if not self.db_path.is_file():
            return []
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                f"""
                SELECT {_SNAPSHOT_SELECT}
                FROM snapshots
                WHERE timestamp_end IS NULL
                ORDER BY timestamp_start ASC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def list_snapshots(
        self,
        *,
        limit: int = 20,
        spec_path: str | None = None,
        file_path: str | None = None,
    ) -> list[dict[str, object]]:
        if not self.db_path.is_file():
            return []
        limit = max(1, min(limit, 500))
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            if file_path:
                rel = normalize_repo_path(file_path)
                rows = conn.execute(
                    f"""
                    SELECT DISTINCT {_SNAPSHOT_SELECT_S}
                    FROM snapshots s
                    INNER JOIN file_deltas fd ON fd.delegation_id = s.delegation_id
                    WHERE fd.path = ?
                    ORDER BY s.timestamp_end DESC, s.timestamp_start DESC
                    LIMIT ?
                    """,
                    (rel, limit),
                ).fetchall()
            elif spec_path:
                rows = conn.execute(
                    f"""
                    SELECT {_SNAPSHOT_SELECT}
                    FROM snapshots
                    WHERE spec_path = ?
                    ORDER BY timestamp_end DESC, timestamp_start DESC
                    LIMIT ?
                    """,
                    (spec_path, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    f"""
                    SELECT {_SNAPSHOT_SELECT}
                    FROM snapshots
                    ORDER BY timestamp_end DESC, timestamp_start DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
        return [dict(row) for row in rows]

    def get_file_history_rows(
        self,
        file_path: str,
        *,
        limit: int = 20,
    ) -> list[dict[str, object]]:
        if not self.db_path.is_file():
            return []
        rel = normalize_repo_path(file_path)
        limit = max(1, min(limit, 500))
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT
                    s.delegation_id,
                    s.checkpoint_summary,
                    s.spec_path,
                    s.spec_report_path,
                    s.timestamp_end,
                    fd.change_type,
                    fd.diff,
                    fd.is_binary
                FROM file_deltas fd
                INNER JOIN snapshots s ON s.delegation_id = fd.delegation_id
                WHERE fd.path = ?
                ORDER BY s.timestamp_end DESC, s.timestamp_start DESC
                LIMIT ?
                """,
                (rel, limit),
            ).fetchall()
        return [dict(row) for row in rows]

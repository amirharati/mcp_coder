from __future__ import annotations

import sqlite3
from pathlib import Path

from core.workspace.manifest import DelegationDelta, Manifest


def _history_db_path(workspace: str | Path) -> Path:
    from core.storage.paths import workspace_history_db_path

    return workspace_history_db_path(workspace)


class WorkspaceHistoryDB:
    """SQLite persistence for delegation workspace snapshots (v1 — no blobs)."""

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
                PRIMARY KEY (delegation_id, path)
            );
            """
        )

    def begin_snapshot(
        self,
        *,
        delegation_id: str,
        mcp_session_id: str,
        timestamp_start: str,
        spec_path: str | None,
        before_manifest: Manifest,
    ) -> None:
        self._before_manifest = before_manifest
        with self._connect() as conn:
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

    def commit_snapshot(
        self,
        *,
        delegation_id: str,
        timestamp_end: str,
        delta: DelegationDelta,
        after_manifest: Manifest,
    ) -> None:
        before = self._before_manifest or {}
        with self._connect() as conn:
            conn.execute(
                "UPDATE snapshots SET timestamp_end = ? WHERE delegation_id = ?",
                (timestamp_end, delegation_id),
            )
            for path in delta.created:
                entry = after_manifest[path]
                conn.execute(
                    """
                    INSERT INTO file_deltas (
                        delegation_id, path, change_type,
                        content_hash, prev_hash, is_binary
                    ) VALUES (?, ?, 'created', ?, NULL, ?)
                    """,
                    (delegation_id, path, entry.content_hash, int(entry.is_binary)),
                )
            for path in delta.modified:
                after_entry = after_manifest[path]
                before_entry = before[path]
                conn.execute(
                    """
                    INSERT INTO file_deltas (
                        delegation_id, path, change_type,
                        content_hash, prev_hash, is_binary
                    ) VALUES (?, ?, 'modified', ?, ?, ?)
                    """,
                    (
                        delegation_id,
                        path,
                        after_entry.content_hash,
                        before_entry.content_hash,
                        int(after_entry.is_binary),
                    ),
                )
            for path in delta.deleted:
                before_entry = before[path]
                conn.execute(
                    """
                    INSERT INTO file_deltas (
                        delegation_id, path, change_type,
                        content_hash, prev_hash, is_binary
                    ) VALUES (?, ?, 'deleted', NULL, ?, ?)
                    """,
                    (
                        delegation_id,
                        path,
                        before_entry.content_hash,
                        int(before_entry.is_binary),
                    ),
                )
            conn.commit()

    def get_file_deltas(self, delegation_id: str) -> list[dict[str, object]]:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT path, change_type, content_hash, prev_hash, is_binary
                FROM file_deltas
                WHERE delegation_id = ?
                ORDER BY path
                """,
                (delegation_id,),
            ).fetchall()
        return [dict(row) for row in rows]

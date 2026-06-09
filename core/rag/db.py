from __future__ import annotations

import sqlite3
from pathlib import Path

from core.rag.models import DelegationIndexRow
from core.storage.paths import delegation_rag_db_path, normalize_workspace


_SCHEMA = """
CREATE TABLE IF NOT EXISTS delegation_index (
    delegation_id      TEXT PRIMARY KEY,
    workspace_path     TEXT NOT NULL,
    timestamp_end      TEXT,
    spec_path          TEXT,
    spec_report_path   TEXT,
    checkpoint_summary TEXT,
    task_preview       TEXT,
    delegate_mode      TEXT,
    outcome            TEXT,
    files_changed      TEXT,
    searchable_text    TEXT NOT NULL
);

CREATE VIRTUAL TABLE IF NOT EXISTS delegation_fts USING fts5(
    delegation_id UNINDEXED,
    searchable_text,
    content='delegation_index',
    content_rowid='rowid'
);

CREATE TRIGGER IF NOT EXISTS delegation_index_ai AFTER INSERT ON delegation_index BEGIN
    INSERT INTO delegation_fts(rowid, delegation_id, searchable_text)
    VALUES (new.rowid, new.delegation_id, new.searchable_text);
END;

CREATE TRIGGER IF NOT EXISTS delegation_index_ad AFTER DELETE ON delegation_index BEGIN
    INSERT INTO delegation_fts(delegation_fts, rowid, delegation_id, searchable_text)
    VALUES('delete', old.rowid, old.delegation_id, old.searchable_text);
END;

CREATE TRIGGER IF NOT EXISTS delegation_index_au AFTER UPDATE ON delegation_index BEGIN
    INSERT INTO delegation_fts(delegation_fts, rowid, delegation_id, searchable_text)
    VALUES('delete', old.rowid, old.delegation_id, old.searchable_text);
    INSERT INTO delegation_fts(rowid, delegation_id, searchable_text)
    VALUES (new.rowid, new.delegation_id, new.searchable_text);
END;
"""


class DelegationRagDB:
    """Per-project SQLite FTS5 index for delegation recall."""

    def __init__(self, workspace: str | Path) -> None:
        self.workspace = normalize_workspace(workspace)
        self.db_path = delegation_rag_db_path(workspace)

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(_SCHEMA)
        return conn

    def upsert(self, row: DelegationIndexRow) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO delegation_index (
                    delegation_id, workspace_path, timestamp_end, spec_path,
                    spec_report_path, checkpoint_summary, task_preview,
                    delegate_mode, outcome, files_changed, searchable_text
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row.delegation_id,
                    row.workspace_path,
                    row.timestamp_end,
                    row.spec_path,
                    row.spec_report_path,
                    row.checkpoint_summary,
                    row.task_preview,
                    row.delegate_mode,
                    row.outcome,
                    row.files_changed,
                    row.searchable_text,
                ),
            )
            conn.commit()

    def has_delegation(self, delegation_id: str) -> bool:
        if not self.db_path.is_file():
            return False
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM delegation_index WHERE delegation_id = ?",
                (delegation_id,),
            ).fetchone()
        return row is not None

    def row_count(self) -> int:
        if not self.db_path.is_file():
            return 0
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) FROM delegation_index").fetchone()
        return int(row[0]) if row else 0

    def last_indexed_timestamp(self) -> str | None:
        if not self.db_path.is_file():
            return None
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT timestamp_end FROM delegation_index
                WHERE timestamp_end IS NOT NULL
                ORDER BY timestamp_end DESC
                LIMIT 1
                """
            ).fetchone()
        return str(row[0]) if row and row[0] else None

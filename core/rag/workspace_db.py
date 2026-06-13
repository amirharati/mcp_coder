from __future__ import annotations

import sqlite3
from pathlib import Path

from core.rag.models import WorkspaceFileIndexRow
from core.storage.paths import normalize_workspace, workspace_rag_db_path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS workspace_file_index (
    path             TEXT PRIMARY KEY,
    sha256           TEXT NOT NULL,
    llm_summary      TEXT,
    symbol_list      TEXT,
    searchable_text  TEXT NOT NULL,
    indexed_at       TEXT NOT NULL
);

CREATE VIRTUAL TABLE IF NOT EXISTS workspace_file_fts USING fts5(
    path UNINDEXED,
    searchable_text,
    content='workspace_file_index',
    content_rowid='rowid'
);

CREATE TRIGGER IF NOT EXISTS workspace_file_index_ai AFTER INSERT ON workspace_file_index BEGIN
    INSERT INTO workspace_file_fts(rowid, path, searchable_text)
    VALUES (new.rowid, new.path, new.searchable_text);
END;

CREATE TRIGGER IF NOT EXISTS workspace_file_index_ad AFTER DELETE ON workspace_file_index BEGIN
    INSERT INTO workspace_file_fts(workspace_file_fts, rowid, path, searchable_text)
    VALUES('delete', old.rowid, old.path, old.searchable_text);
END;

CREATE TRIGGER IF NOT EXISTS workspace_file_index_au AFTER UPDATE ON workspace_file_index BEGIN
    INSERT INTO workspace_file_fts(workspace_file_fts, rowid, path, searchable_text)
    VALUES('delete', old.rowid, old.path, old.searchable_text);
    INSERT INTO workspace_file_fts(rowid, path, searchable_text)
    VALUES (new.rowid, new.path, new.searchable_text);
END;
"""


class WorkspaceRagDB:
    """Per-project SQLite FTS5 index for workspace source files."""

    def __init__(self, workspace: str | Path) -> None:
        self.workspace = normalize_workspace(workspace)
        self.db_path = workspace_rag_db_path(workspace)

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(_SCHEMA)
        return conn

    def upsert(self, row: WorkspaceFileIndexRow) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO workspace_file_index (
                    path, sha256, llm_summary, symbol_list, searchable_text, indexed_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    row.path,
                    row.sha256,
                    row.llm_summary,
                    row.symbol_list,
                    row.searchable_text,
                    row.indexed_at,
                ),
            )
            conn.commit()

    def get_sha256(self, path: str) -> str | None:
        if not self.db_path.is_file():
            return None
        with self._connect() as conn:
            row = conn.execute(
                "SELECT sha256 FROM workspace_file_index WHERE path = ?",
                (path,),
            ).fetchone()
        return str(row[0]) if row and row[0] else None

    def list_paths(self) -> set[str]:
        if not self.db_path.is_file():
            return set()
        with self._connect() as conn:
            rows = conn.execute("SELECT path FROM workspace_file_index").fetchall()
        return {str(r[0]) for r in rows}

    def delete_paths(self, paths: set[str]) -> int:
        if not paths or not self.db_path.is_file():
            return 0
        with self._connect() as conn:
            cur = conn.executemany(
                "DELETE FROM workspace_file_index WHERE path = ?",
                [(p,) for p in sorted(paths)],
            )
            conn.commit()
        return cur.rowcount if cur.rowcount is not None else len(paths)

    def row_count(self) -> int:
        if not self.db_path.is_file():
            return 0
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) FROM workspace_file_index").fetchone()
        return int(row[0]) if row else 0

"""Workspace-file FTS search (P5-003)."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from core.config.rag import workspace_file_rag_enabled
from core.rag.fts import fts_match_query
from core.rag.models import WorkspaceFileHit
from core.storage.paths import workspace_rag_db_path

_MIN_QUERY_LEN = 2
_DEFAULT_LIMIT = 5
_MAX_LIMIT = 20


def workspace_search(
    workspace: str | Path,
    query: str,
    *,
    limit: int = _DEFAULT_LIMIT,
) -> list[WorkspaceFileHit]:
    if not workspace_file_rag_enabled(workspace):
        return []

    q = query.strip()
    if len(q) < _MIN_QUERY_LEN:
        return []

    limit = max(1, min(limit, _MAX_LIMIT))
    fts_q = fts_match_query(q)
    if not fts_q:
        return []

    db_path = workspace_rag_db_path(workspace)
    if not db_path.is_file():
        return []

    sql = """
        SELECT
            w.path,
            w.sha256,
            w.llm_summary,
            w.symbol_list,
            w.indexed_at,
            bm25(workspace_file_fts) AS bm25_score
        FROM workspace_file_fts
        JOIN workspace_file_index w ON w.rowid = workspace_file_fts.rowid
        WHERE workspace_file_fts MATCH ?
        ORDER BY bm25_score
        LIMIT ?
    """
    hits: list[WorkspaceFileHit] = []
    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(sql, (fts_q, limit)).fetchall()
        except sqlite3.OperationalError:
            return []

    for row in rows:
        relevance = -float(row["bm25_score"])
        hits.append(
            WorkspaceFileHit(
                path=str(row["path"]),
                score=relevance,
                sha256=str(row["sha256"]) if row["sha256"] else None,
                llm_summary=str(row["llm_summary"]) if row["llm_summary"] else None,
                symbol_list=str(row["symbol_list"]) if row["symbol_list"] else None,
                indexed_at=str(row["indexed_at"]) if row["indexed_at"] else None,
            )
        )

    hits.sort(key=lambda h: h.score, reverse=True)
    return hits[:limit]


def workspace_search_for_mcp(
    workspace: str | Path,
    query: str,
    *,
    limit: int = _DEFAULT_LIMIT,
) -> dict[str, Any]:
    if not workspace_file_rag_enabled(workspace):
        return {"found": False, "error": "workspace file RAG disabled"}

    q = query.strip()
    if len(q) < _MIN_QUERY_LEN:
        return {"found": False, "error": "query must be at least 2 characters"}

    db_path = workspace_rag_db_path(workspace)
    if not db_path.is_file():
        return {"found": False, "error": "workspace_rag.db not found"}

    hits = workspace_search(workspace, q, limit=limit)
    return {
        "found": True,
        "query": q,
        "hits": [h.to_dict() for h in hits],
    }
